import os
import sys

import yaml

from .common import get_workspace_dir, print_workspace_state


def init_command(args):
    workspace = os.path.abspath(args.workspace)

    existing = get_workspace_dir(workspace)
    if existing is not None:
        print(f'Error: An existing workspace already exists in this path: {existing}')
        sys.exit(1)

    if not os.path.exists(workspace):
        print(f"Error: The specified workspace directory '{workspace}' does not exist.")
        sys.exit(1)

    src_dir = os.path.join(workspace, "src")
    if not os.path.exists(src_dir):
        print(f"Error: The specified workspace directory '{workspace}' does not contain a "
              f"'src' directory'.")
        sys.exit(1)

    print(f"Initializing workspace at '{workspace}'...")

    profiles_dir = os.path.join(workspace, ".hatch", "profiles")
    os.makedirs(profiles_dir, exist_ok=True)

    profiles_file = os.path.join(profiles_dir, "profiles.yaml")
    if os.path.exists(profiles_file):
        print(f"Workspace has already been initialized.\n")
        print_workspace_state(workspace)
        sys.exit(0)

    default_profile_dir = os.path.join(profiles_dir, "default")
    os.makedirs(default_profile_dir, exist_ok=True)

    config_file = os.path.join(default_profile_dir, "config.yaml")
    if os.path.exists(config_file):
        print(f"Workspace has already been initialized.\n")
        print_workspace_state(workspace)
        sys.exit(0)

    config_content = {
        "build_space": "build",
        "colcon_build_args": [],
        "nice": 0,
        "extend_path": "",
        "install_space": "install",
        "test_result_space": "test_results"
    }

    with open(config_file, "w") as f:
        yaml.dump(config_content, f, default_flow_style=False)

    with open(profiles_file, "w") as f:
        yaml.dump({"active": "default"}, f, default_flow_style=False)

    print_workspace_state(workspace)
    sys.exit(0)
