import os
import sys

import yaml

from .common import (get_workspace_dir, get_active_profile, remove_duplicates,
                     print_workspace_state)


def config_command(args):
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

    if not os.path.exists(profile_dir):
        print(f"Error: Profile '{profile}' does not exist.")
        sys.exit(1)

    config_content = {
        "build_space": "build",
        "colcon_build_args": [],
        "nice": 0,
        "extend_path": "",
        "install_space": "install",
        "test_result_space": "test_results"
    }

    if os.path.exists(config_file):
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
