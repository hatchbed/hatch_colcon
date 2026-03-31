import os
import shutil
import sys
import textwrap

import yaml

from .common import (get_workspace_dir, get_active_profile, get_package,
                     get_dependent_packages, delete_matching_dirs)


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
