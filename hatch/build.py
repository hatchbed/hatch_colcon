import os
import subprocess
import sys
import time

from .common import get_workspace_dir, get_active_profile, get_package


def register(subparsers):
    parser = subparsers.add_parser("build", help="Builds a colcon workspace.")
    parser.add_argument("--workspace", "-w", default=".",
                        help="The path to the colcon workspace (default: \".\")")
    parser.add_argument("--profile", default="default",
                        help="The name of a config profile to use (default: 'default')")
    packages_group = parser.add_argument_group(
        'Packages', 'Clean workspace subdirectories for the selected profile.')
    packages_group.add_argument(
        "pkgs", metavar="PKGNAME", nargs='*', type=str,
        help='Explicilty specify a list of specific packages to build.')
    packages_group.add_argument(
        "--this", action="store_true",
        help="Build the package containing the current working directory.")
    packages_group.add_argument(
        "--no-deps", action="store_true",
        help="Only build specified packages, not their dependencies.")
    config_group = parser.add_argument_group('Config', "Parameters for the underlying build system.")
    config_group.add_argument(
        "--colcon-build-args", metavar='ARG', dest='colcon_build_args',
        nargs="+", required=False, type=str, default=None,
        help="Additional arguments for colcon")
    config_group.add_argument(
        "--nice", "-n", type=int, help="CPU niceness for build commands. (default: 0)")
    parser.set_defaults(func=build_command)


def build_command(args):
    workspace = os.path.abspath(args.workspace)

    if not os.path.exists(workspace):
        print(f"Error: The specified workspace directory '{workspace}' does not exist.")
        sys.exit(1)

    workspace = get_workspace_dir(workspace)
    if workspace is None:
        print(f"Error: Parent colcon workspace directory does not exist.")
        sys.exit(1)

    profile = args.profile
    if profile is None:
        profile = get_active_profile(workspace)
        if profile is None:
            print(f"Workspace '{workspace}' has not been initialized with an active profile.")
            return

    profile_dir = os.path.join(workspace, ".hatch", "profiles", profile)
    config_file = os.path.join(profile_dir, "config.yaml")

    if not os.path.exists(config_file):
        print(f"Error: Profile '{profile}' does not exist.")
        sys.exit(1)

    import yaml
    config_content = {
        "build_space": "build",
        "colcon_build_args": [],
        "nice": 0,
        "extend_path": "",
        "install_space": "install",
        "test_result_space": "test_results"
    }
    with open(config_file, "r") as f:
        config_content.update(yaml.safe_load(f))

    colcon_cmd = ["colcon", "build"]

    build_space = config_content.get("build_space", "build") or "build"
    colcon_cmd += ['--build-base', build_space]

    install_space = config_content.get("install_space", "install") or "install"
    colcon_cmd += ['--install-base', install_space]

    test_result_space = config_content.get("test_result_space", "test_results") or "test_results"
    colcon_cmd += ['--test-result-base', test_result_space]

    colcon_build_args = config_content.get("colcon_build_args", []) or []
    if args.colcon_build_args:
        colcon_build_args = args.colcon_build_args

    nice = config_content.get("nice", 0) or 0
    if args.nice is not None:
        nice = args.nice

    colcon_cmd += colcon_build_args

    packages = args.pkgs
    if args.this:
        current_package = get_package(args.workspace)
        if current_package:
            packages.append(current_package)

    if packages:
        if args.no_deps:
            colcon_cmd += ['--packages-select'] + packages
        else:
            colcon_cmd += ['--packages-up-to'] + packages

    colcon_shell_cmd = ' '.join(colcon_cmd)

    extend_path = config_content.get("extend_path", None)
    if extend_path:
        extend_script = os.path.join(extend_path, "setup.bash")
        if not os.path.exists(extend_script):
            print(f"Error: '{extend_script}' does not exist.")
            sys.exit(1)
        colcon_shell_cmd = f'source {extend_script} && ' + colcon_shell_cmd

    print(f"Running: {colcon_shell_cmd}")

    process = subprocess.Popen(
        colcon_shell_cmd,
        cwd=workspace,
        shell=True,
        executable="/bin/bash",
        stdout=sys.stdout,
        stderr=sys.stderr,
        env={}
    )

    while process.poll() is None:
        subprocess.run(
            f"renice -n {nice} -p $(pgrep -g $(ps -o pgid= -p {process.pid}))",
            shell=True,
            executable="/bin/bash",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        time.sleep(1)
