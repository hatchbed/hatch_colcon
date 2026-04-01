import os
import sys

import yaml

from .common import (get_workspace_dir, remove_duplicates, print_workspace_state)


def register(subparsers):
    parser = subparsers.add_parser("config", help="Configures a colcon workspace's context.")
    parser.add_argument("--workspace", "-w", default=".",
                        help="The path to the colcon workspace (default: \".\")")
    behavior_group = parser.add_argument_group('Behavior', 'Options affecting argument handling.')
    behavior_group.add_argument("--append-args", "-a", action="store_true",
                                help="Append elements to list-type arguments")
    behavior_group.add_argument("--remove-args", "-r", action="store_true",
                                help="Remove elements from list-type arguments")
    context_group = parser.add_argument_group(
        'Workspace Context', 'Options affecting the context of the workspace.')
    context_group.add_argument("--extend", "-e",
                               help="Extend the result-space of another colcon workspace")
    context_group.add_argument("--no-extend", action="store_true",
                               help="Unset the explicit extension of another workspace")
    spaces_group = parser.add_argument_group('Spaces', 'Location of parts of the colcon workspace.')
    spaces_group.add_argument("--build-space", "--build", "-b", help="Path to the build space")
    spaces_group.add_argument("--default-build-space", action="store_true",
                              help="Use the default build space ('build')")
    spaces_group.add_argument("--install-space", "--install", "-i",
                              help="Path to the install space")
    spaces_group.add_argument("--default-install-space", action="store_true",
                              help="Use the default install space ('install')")
    spaces_group.add_argument("--test-result-space", "--test", "-t",
                              help="Path to the test result space")
    spaces_group.add_argument("--default-test-result-space", action="store_true",
                              help="Use the default test result space ('test_results')")
    spaces_group.add_argument("--space-suffix", "-x",
                              help="Suffix for build, test results, and install space")
    build_group = parser.add_argument_group(
        'Build Options', 'Options for configuring the way packages are built.')
    build_group.add_argument("--no-colcon-build-args", action="store_true",
                             help="Pass no additional arguments to colcon")
    build_group.add_argument(
        "--colcon-build-args", metavar='ARG', dest='colcon_build_args',
        nargs="+", required=False, type=str, default=None,
        help="Additional arguments for colcon")
    build_group.add_argument("--nice", "-n", type=int,
                             help="CPU niceness for build commands. (default: 0)")
    parser.set_defaults(func=config_command)


def config_command(args):
    workspace = os.path.abspath(args.workspace)

    if not os.path.exists(workspace):
        print(f"Error: The specified workspace directory '{workspace}' does not exist.")
        sys.exit(1)

    workspace = get_workspace_dir(workspace)
    if workspace is None:
        print(f"Error: Parent colcon workspace directory does not exist.")
        sys.exit(1)

    config_file = os.path.join(workspace, ".hatch", "config.yaml")

    if not os.path.exists(config_file):
        print(f"Error: Workspace has not been initialized. Run 'hatch init' first.")
        sys.exit(1)

    config_content = {
        "build_space": "build",
        "colcon_build_args": [],
        "nice": 0,
        "extend_path": "",
        "install_space": "install",
        "test_result_space": "test_results"
    }

    with open(config_file, "r") as f:
        config_content = yaml.safe_load(f)

    if args.extend:
        config_content['extend_path'] = args.extend
    elif args.no_extend:
        config_content['extend_path'] = ""

    if args.build_space:
        config_content['build_space'] = args.build_space
    elif args.default_build_space:
        config_content['build_space'] = "build"

    if args.install_space:
        config_content['install_space'] = args.install_space
    elif args.default_install_space:
        config_content['install_space'] = "install"

    if args.test_result_space:
        config_content['test_result_space'] = args.test_result_space
    elif args.default_test_result_space:
        config_content['test_result_space'] = "test_results"

    if args.space_suffix:
        if config_content["build_space"] == "build":
            config_content["build_space"] = "build" + args.space_suffix
        if config_content["install_space"] == "install":
            config_content["install_space"] = "install" + args.space_suffix
        if config_content["test_result_space"] == "test_results":
            config_content["test_result_space"] = "test_results" + args.space_suffix

    if args.colcon_build_args:
        colcon_args = config_content.get('colcon_build_args', []) or []
        if args.append_args:
            config_content['colcon_build_args'] = colcon_args + args.colcon_build_args
        elif args.remove_args and config_content['colcon_build_args']:
            config_content['colcon_build_args'] = [
                a for a in colcon_args if a not in args.colcon_build_args]
        else:
            config_content['colcon_build_args'] = args.colcon_build_args
        config_content['colcon_build_args'] = remove_duplicates(
            config_content['colcon_build_args'])

    if args.no_colcon_build_args:
        config_content['colcon_build_args'] = []

    if args.nice:
        config_content['nice'] = args.nice

    with open(config_file, "w") as f:
        yaml.dump(config_content, f, default_flow_style=False)

    print_workspace_state(workspace)
    sys.exit(0)
