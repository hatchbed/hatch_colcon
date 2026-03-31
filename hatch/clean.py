import os
import shutil
import sys
import textwrap

import yaml

from .common import (get_workspace_dir, get_active_profile, get_package,
                     get_dependent_packages, delete_matching_dirs)


def register(subparsers):
    parser = subparsers.add_parser("clean", help="Deletes various products of the build verb.")
    parser.add_argument("--workspace", "-w", default=".",
                        help="The path to the colcon workspace (default: \".\")")
    parser.add_argument("--profile", default="default",
                        help="The name of a config profile to use (default: 'default')")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Assume \"yes\" to all interactive checks.")
    parser.add_argument(
        "--all-profiles", "-a", action="store_true",
        help="Apply the specified clean operation for all profiles in this workspace.")
    parser.add_argument(
        "--deinit", action="store_true",
        help="De-initialize the workspace, delete all build profiles and configuration. "
             "This will also clean subdirectories for all profiles in the workspace.")
    spaces_group = parser.add_argument_group(
        'Spaces', 'Clean workspace subdirectories for the selected profile.')
    spaces_group.add_argument("--build-space", "--build", "-b", action="store_true",
                              help="Remove the entire build space")
    spaces_group.add_argument("--install-space", "--install", "-i", action="store_true",
                              help="Remove the entire install space")
    spaces_group.add_argument("--test-result-space", "--test", "-t", action="store_true",
                              help="Remove the entire test result space")
    spaces_group.add_argument("--log-space", "--logs", "-l", action="store_true",
                              help="Remove the entire log space")
    packages_group = parser.add_argument_group(
        'Packages', 'Clean workspace subdirectories for the selected profile.')
    packages_group.add_argument(
        "pkgs", metavar="PKGNAME", nargs='*', type=str,
        help='Explicilty specify a list of specific packages to clean from the build, '
             'devel, and install space.')
    packages_group.add_argument(
        "--this", action="store_true",
        help="Clean the package containing the current working directory from the build "
             "and install space.")
    packages_group.add_argument(
        "--dependents", "--dep", action="store_true",
        help="Clean the packages which depend on the packages to be cleaned.")
    parser.set_defaults(func=clean_command)


def clean_command(args):
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

    config_content = {
        "build_space": "build",
        "install_space": "install",
        "test_result_space": "test_results"
    }
    with open(config_file, "r") as f:
        config_content.update(yaml.safe_load(f))

    build_space = config_content.get("build_space", "build") or "build"
    install_space = config_content.get("install_space", "install") or "install"
    test_result_space = config_content.get("test_result_space", "test_results") or "test_results"

    targets = []
    if args.build_space:
        targets.append(build_space)
    if args.install_space:
        targets.append(install_space)
    if args.test_result_space:
        targets.append(test_result_space)
    if args.log_space:
        targets.append("log")
    if len(targets) == 0:
        targets = [build_space, install_space, test_result_space, "log"]

    target_paths = [
        os.path.join(workspace, t)
        for t in targets
        if os.path.isdir(os.path.join(workspace, t))
    ]

    if len(target_paths) == 0:
        print("Nothing to clean.")
        return

    packages = args.pkgs
    if args.this:
        current_package = get_package(args.workspace)
        if current_package:
            packages.append(current_package)

    if len(packages) > 0 and args.dependents:
        packages = get_dependent_packages(packages)

    if len(packages) > 0:
        print("Cleaning the following packages:")
        pkgs_str = textwrap.fill(' '.join(packages), width=70)
        pkgs_str = "\n".join(['    ' + line for line in pkgs_str.splitlines()])
        print(f"{pkgs_str}")
        print("  from:")
        print("\n".join(['    ' + t for t in target_paths]))
    else:
        print("Cleaning:")
        print("\n".join(['    ' + t for t in target_paths]))

    if not args.yes:
        response = input("Are you sure you want to continue? (y/N): ").strip().lower()
        if response not in ("y", "yes"):
            print("Aborting.")
            exit(1)

    if len(packages) > 0:
        for target_path in target_paths:
            delete_matching_dirs(target_path, packages)
    else:
        for target_path in target_paths:
            shutil.rmtree(target_path)
