#!/usr/bin/env python3

import argparse
from datetime import date
import os
import pkg_resources
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import yaml

def remove_duplicates(lst):
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]


def split_arguments(args, splitter_index):
    start_index = splitter_index + 1
    end_index = args.index('--', start_index) if '--' in args[start_index:] else None

    if end_index:
        return (
            args[0:splitter_index],
            args[start_index:end_index],
            args[(end_index + 1):]
        )
    else:
        return (
            args[0:splitter_index],
            args[start_index:],
            []
        )


def get_colcon_build_args(verb, args):
    if verb not in ['build', 'config', 'test']:
        return args, []

    ordered_splitters = reversed([(i, t) for i, t in enumerate(args) if t in ['--colcon-build-args']])

    head_args = args
    tail_args = []
    colcon_build_args = []
    for index, name in ordered_splitters:
        head_args, colcon_args, tail = split_arguments(head_args, splitter_index=index)
        tail_args.extend(tail)
        colcon_build_args.extend(colcon_args)

    args = head_args + tail_args
    return args, colcon_build_args

def get_active_profile(workspace):
    hatch_dir = os.path.join(workspace, ".hatch")
    profiles_dir = os.path.join(hatch_dir, "profiles")
    profiles_file = os.path.join(profiles_dir, "profiles.yaml")
    if os.path.exists(profiles_file):
        with open(profiles_file, "r") as f:
            profiles = yaml.safe_load(f)
            active = profiles.get('active', "")
            if len(active) > 0:
                return active
    
    return None

def get_workspace_dir(current_dir):
    # Normalize the path to handle different path representations
    current_dir = os.path.abspath(current_dir)
    
    # Continue searching until we reach the root directory
    while current_dir != os.path.dirname(current_dir):
        # Check for the specific paths
        src_path = os.path.join(current_dir, 'src')
        profiles_path = os.path.join(current_dir, '.hatch', 'profiles', 'profiles.yaml')
        
        # Check if both paths exist
        if (os.path.isdir(src_path) and 
            os.path.isfile(profiles_path)):
            return current_dir
        
        # Move to the parent directory
        current_dir = os.path.dirname(current_dir)
    
    # If we've reached the root without finding the workspace, return None
    return None


def parse_package_name(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        if root.tag != "package":
            return None

        name_element = root.find("name")
        if name_element is None:
            return None

        return name_element.text.strip() if name_element.text else None

    except:
        return None

    return None

def get_package(current_dir):
    # Normalize the path to handle different path representations
    current_dir = os.path.abspath(current_dir)
    
    # Continue searching until we reach the root directory
    while current_dir != os.path.dirname(current_dir):
        # Check for the specific paths
        package_file = os.path.join(current_dir, 'package.xml')
        
        # Check if both paths exist
        if os.path.isfile(package_file):
            name = parse_package_name(package_file)
            if name:
                return name
        
        # Move to the parent directory
        current_dir = os.path.dirname(current_dir)
    
    # If we've reached the root without finding the workspace, return None
    return None

def print_workspace_state(workspace):
    # Define the paths to check

    src_dir = os.path.join(workspace, "src")

    # Get the current profile directory
    hatch_dir = os.path.join(workspace, ".hatch")
    profiles_dir = os.path.join(hatch_dir, "profiles")

    active_profile = get_active_profile(workspace)
    if active_profile is None:
        print(f"Workspace '{workspace}'' has not been initialized with an active profile.")
        return

    active_profile_dir = os.path.join(profiles_dir, active_profile)
    config_file = os.path.join(active_profile_dir, "config.yaml")
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
            colcon_build_args = config.get('colcon_build_args', [])
            extend_path = config.get('extend_path', "")
            if extend_path is not None and len(extend_path.strip()) == 0:
                extend_path = None
            build_space = config.get("build_space", "build")
            if build_space is None or len(build_space.strip()) == 0:
                build_space = "build"
            install_space = config.get("install_space", "install")
            if install_space is None or len(install_space.strip()) == 0:
                install_space = "install"
            test_result_space = config.get("test_result_space", "test_results")
            if test_result_space is None or len(test_result_space.strip()) == 0:
                test_result_space = "test_results"
            nice = config.get("nice", 0)
            if nice is None:
                nice = 0

    build_dir = os.path.join(workspace, build_space)
    install_dir = os.path.join(workspace, install_space)
    test_results_dir = os.path.join(workspace, test_result_space)

    env_extend_path = os.environ.get("COLCON_PREFIX_PATH", None)

    print("-" * 70)
    print(f"Profile:                     {active_profile}")
    if extend_path is None:
        if env_extend_path is None:
            print(f"Extending: ")
        else:
            print(f"Extending:             [env] {env_extend_path}")
    else:
        print(f"Extending:                   {extend_path}")
    print(f"Workspace:                   {workspace}")
    print("-" * 70)

    # Check if the spaces exist and display their status
    print(f"Build Space:       {' [exists]' if os.path.exists(build_dir) else '[missing]'} {build_dir}")
    print(f"Install Space:     {' [exists]' if os.path.exists(install_dir) else '[missing]'} {install_dir}")
    print(f"Test Result Space: {' [exists]' if os.path.exists(test_results_dir) else '[missing]'} {test_results_dir}")
    print(f"Source Space:      {' [exists]' if os.path.exists(src_dir) else '[missing]'} {src_dir}")
    print("-" * 70)

    # Print additional args
    print(f"CPU Niceness                 {nice}")
    if not colcon_build_args:
        print(f"Colcon Build Args:           None")
    else:
        print(f"Colcon Build Args:           {colcon_build_args[0]}")
        for arg in colcon_build_args[1:]:
            print(f"                             {arg}")
    print("-" * 70)


def init_command(args):
    workspace = os.path.abspath(args.workspace)

    existing = get_workspace_dir(workspace)
    if existing is not None:
        print(f'Error: An existing workspace already exists in this path: {existing}')
        sys.exit(1)

    # Check if the workspace directory exists
    if not os.path.exists(workspace):
        print(f"Error: The specified workspace directory '{workspace}' does not exist.")
        sys.exit(1)

    src_dir = os.path.join(workspace, "src")
    if not os.path.exists(src_dir):
        print(f"Error: The specified workspace directory '{workspace}' does not contain a 'src' directory'.")
        sys.exit(1)

    # If directory exists, proceed with initialization (stub for now)
    print(f"Initializing workspace at '{workspace}'...")
    
    hatch_dir = os.path.join(workspace, ".hatch")
    os.makedirs(hatch_dir, exist_ok=True)

    profiles_dir = os.path.join(hatch_dir, "profiles")
    os.makedirs(profiles_dir, exist_ok=True)

    profiles_file = os.path.join(profiles_dir, "profiles.yaml")
    if os.path.exists(profiles_file):
        print(f"Workspace has already been initialized.\n")
        print_workspace_state(workspace)
        sys.exit(0)

    default_profile_dir = os.path.join(profiles_dir, "default")
    os.makedirs(default_profile_dir, exist_ok=True)

    # Check if config.yaml exists
    config_file = os.path.join(default_profile_dir, "config.yaml")
    if os.path.exists(config_file):
        print(f"Workspace has already been initialized.\n")
        print_workspace_state(workspace)
        sys.exit(0)

    # Prepare the default content for config.yaml
    config_content = {
        "build_space": "build",
        "colcon_build_args": [],
        "nice": 0,
        "extend_path": "",
        "install_space": "install",
        "test_result_space": "test_results"
    }

    # Create the config.yaml file
    with open(config_file, "w") as f:
        yaml.dump(config_content, f, default_flow_style=False)

    # Create the profiles.yaml file
    with open(profiles_file, "w") as f:
        yaml.dump({"active": "default"}, f, default_flow_style=False)

    print_workspace_state(workspace)
    sys.exit(0)

def config_command(args):
    workspace = os.path.abspath(args.workspace)

    # Check if the workspace directory exists
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

    # Define profile directory
    hatch_dir = os.path.join(workspace, ".hatch")
    profiles_dir = os.path.join(hatch_dir, "profiles")
    profile_dir = os.path.join(profiles_dir, profile)
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
        colcon_args = config_content.get('colcon_build_args', [])
        if colcon_args is None:
            colcon_args = []
        if args.append_args:
            config_content['colcon_build_args'] = colcon_args + args.colcon_build_args
        elif args.remove_args and config_content['colcon_build_args']:
            config_content['colcon_build_args'] = [arg for arg in colcon_args if arg not in args.colcon_build_args]
        else:
            config_content['colcon_build_args'] = args.colcon_build_args
        config_content['colcon_build_args'] = remove_duplicates(config_content['colcon_build_args'])

    if args.no_colcon_build_args:
        config_content['colcon_build_args'] = []

    if args.nice:
        config_content['nice'] = args.nice

    with open(config_file, "w") as f:
        yaml.dump(config_content, f, default_flow_style=False)

    print_workspace_state(workspace)
    sys.exit(0)


def build_command(args):
    # Find the workspace directory
    workspace = os.path.abspath(args.workspace)
    
    # Verify workspace exists
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

    # Define profile directory
    hatch_dir = os.path.join(workspace, ".hatch")
    profiles_dir = os.path.join(hatch_dir, "profiles")
    profile_dir = os.path.join(profiles_dir, profile)
    config_file = os.path.join(profile_dir, "config.yaml")

    if not os.path.exists(config_file):
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
            config_content.update(yaml.safe_load(f))

    colcon_cmd = ["colcon", "build"]

    # Build space
    build_space = config_content.get("build_space", "build")
    if not build_space:
        build_space = "build"
    colcon_cmd += ['--build-base', build_space]

    # Install space
    install_space = config_content.get("install_space", "install")
    if not install_space:
        install_space = "install"
    colcon_cmd += ['--install-base', install_space]

    # Test results space
    test_result_space = config_content.get("test_result_space", "test_results")
    if not test_result_space:
        test_result_space = "test_results"
    colcon_cmd += ['--test-result-base', test_result_space]

    # Extra build args
    colcon_build_args = config_content.get("colcon_build_args", [])
    if colcon_build_args is None:
        colcon_build_args = []
    if args.colcon_build_args:
        colcon_build_args = args.colcon_build_args

    # Nice level
    nice = config_content.get("nice", 0)
    if nice is None:
        nice = 0
    if args.nice is not None:
        nice = args.nice

    colcon_cmd += colcon_build_args

    # Packages
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

    # Extend path
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


def clean_command(args):
    pass

def test_command(args):
    pass

def list_packages_command(args):
    pass

def list_repos_command(args):
    pass

def profile_add(args):
    pass

def profile_remove(args):
    pass

def profile_set(args):
    pass

def profile_rename(args):
    pass

class CustomArgumentParser(argparse.ArgumentParser):
    def format_help(self):
        help_text = super().format_help()
        lines = help_text.splitlines()
        formatted_lines = []
        prev_blank = False

        for line in lines:
            if line.strip():
                formatted_lines.append(line)
                prev_blank = False
            elif not prev_blank:
                formatted_lines.append("")
                prev_blank = True
        

        return "\n".join(formatted_lines) + "\n"

def main():
    parser = CustomArgumentParser(
        prog="hatch",
        description="hatch command",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--version", action="store_true", help="Prints the hatch version.")
    
    subparsers = parser.add_subparsers(dest="command", title="hatch command",
                                       description="Call `hatch VERB -h` for help on each verb listed below:",
                                       metavar="")
    
    builder_parser = subparsers.add_parser("build", help="Builds a colcon workspace.")
    builder_parser.add_argument("--workspace", "-w", default=".", help="The path to the colcon workspace (default: \".\")")
    builder_parser.add_argument("--profile", default="default", help="The name of a config profile to use (default: 'default')")

    build_packages_group = builder_parser.add_argument_group('Packages', 'Clean workspace subdirectories for the selected profile.')
    build_packages_group.add_argument("pkgs", metavar="PKGNAME", nargs='*', type=str, help='Explicilty specify a list of specific packages to clean from the build, devel, and install space.')
    build_packages_group.add_argument("--this", action="store_true", help="Clean the package containing the current working directory from the build and install space.")
    build_packages_group.add_argument("--no-deps", action="store_true", help="Only build specified packages, not their dependencies.")

    build_config_group = builder_parser.add_argument_group('Config', "Parameters for the underlying build system.")
    build_config_group.add_argument("--colcon-build-args", metavar='ARG', dest='colcon_build_args', 
                                    nargs="+", required=False, type=str, default=None, help="Additional arguments for colcon")
    build_config_group.add_argument("--nice", "-n", type=int, help="CPU niceness for build commands. (default: 0)")
    builder_parser.set_defaults(func=build_command)

    clean_parser = subparsers.add_parser("clean", help="Deletes various products of the build verb.")
    clean_parser.add_argument("--workspace", "-w", default=".", help="The path to the colcon workspace (default: \".\")")
    clean_parser.add_argument("--profile", default="default", help="The name of a config profile to use (default: 'default')")
    clean_parser.add_argument("--yes", "-y", action="store_true", help="Assume \"yes\" to all interactive checks.")
    clean_parser.add_argument("--all-profiles", "-a", action="store_true", help="Apply the specified clean operation for all profiles in this workspace.")
    clean_parser.add_argument("--deinit", action="store_true", 
                               help="De-initialize the workspace, delete all build profiles and "
                                    "configuration.  This will also clean subdirectories for all "
                                    "profiles in the workspace.")

    clean_spaces_group = clean_parser.add_argument_group('Spaces', 'Clean workspace subdirectories for the selected profile.')
    clean_spaces_group.add_argument("--build-space", "--build", "-b", action="store_true", help="Remove the entire build space")
    clean_spaces_group.add_argument("--install-space", "--install", "-i", action="store_true", help="Remove the entire install space")
    clean_spaces_group.add_argument("--test-result-space", "--test", "-t", action="store_true", help="Remove the entire test result space")
    clean_spaces_group.add_argument("--log-space", "--logs", "-l", action="store_true", help="Remove the entire log space")

    clean_packages_group = clean_parser.add_argument_group('Packages', 'Clean workspace subdirectories for the selected profile.')
    clean_packages_group.add_argument("pkgs", metavar="PKGNAME", nargs='*', type=str, help='Explicilty specify a list of specific packages to clean from the build, devel, and install space.')
    clean_packages_group.add_argument("--this", action="store_true", help="Clean the package containing the current working directory from the build and install space.")
    clean_packages_group.add_argument("--dependents", "--dep", action="store_true", help="Clean the packages which depend on the packages to be cleaned.")

    clean_parser.set_defaults(func=clean_command)

    ## Config
    config_parser = subparsers.add_parser("config", help="Configures a colcon workspace's context.")
    config_parser.add_argument("--workspace", "-w", default=".", help="The path to the colcon workspace (default: \".\")")
    config_parser.add_argument("--profile", default="default", help="The name of a config profile to use (default: 'default')")

    config_behavior_group = config_parser.add_argument_group('Behavior', 'Options affecting argument handling.')
    config_behavior_group.add_argument("--append-args", "-a", action="store_true", help="Append elements to list-type arguments")
    config_behavior_group.add_argument("--remove-args", "-r", action="store_true", help="Remove elements from list-type arguments")
    
    config_context_group = config_parser.add_argument_group('Workspace Context', 'Options affecting the context of the workspace.')
    config_context_group.add_argument("--extend", "-e", help="Extend the result-space of another colcon workspace")
    config_context_group.add_argument("--no-extend", action="store_true", help="Unset the explicit extension of another workspace")
    
    config_spaces_group = config_parser.add_argument_group('Spaces', 'Location of parts of the colcon workspace.')
    config_spaces_group.add_argument("--build-space", "--build", "-b", help="Path to the build space")
    config_spaces_group.add_argument("--default-build-space", action="store_true", help="Use the default build space ('build')")
    config_spaces_group.add_argument("--install-space", "--install", "-i", help="Path to the install space")
    config_spaces_group.add_argument("--default-install-space", action="store_true", help="Use the default install space ('install')")
    config_spaces_group.add_argument("--test-result-space", "--test", "-t", help="Path to the test result space")
    config_spaces_group.add_argument("--default-test-result-space", action="store_true", help="Use the default test result space ('test_results')")
    config_spaces_group.add_argument("--space-suffix", "-x", help="Suffix for build, test results, and install space")

    config_build_group = config_parser.add_argument_group('Build Options', 'Options for configuring the way packages are built.')
    config_build_group.add_argument("--no-colcon-build-args", action="store_true", help="Pass no additional arguments to colcon")
    config_build_group.add_argument("--colcon-build-args", metavar='ARG', dest='colcon_build_args', 
                                    nargs="+", required=False, type=str, default=None, help="Additional arguments for colcon")
    config_build_group.add_argument("--nice", "-n", type=int, help="CPU niceness for build commands. (default: 0)")
    config_parser.set_defaults(func=config_command)

    ## Init
    init_parser = subparsers.add_parser("init", help="Initializes a given folder as a colcon workspace.")
    init_parser.add_argument("--workspace", "-w", default=".", help="The path to the colcon workspace (default: \".\")")
    init_parser.set_defaults(func=init_command)
    
    ## List
    list_parser = subparsers.add_parser("list", help="Lists colcon packages in the workspace or other arbitrary folders.")
    list_subparsers = list_parser.add_subparsers(dest="list_command")
    list_packages_parser = list_subparsers.add_parser("packages", help="List packages in workspace.")
    list_packages_parser.add_argument("--workspace", "-w", default=".", help="The path to the colcon workspace (default: \".\")")
    list_packages_parser.set_defaults(func=list_packages_command)

    list_repos_parser = list_subparsers.add_parser("repos", help="List repos in workspace.")
    list_repos_parser.add_argument("--workspace", "-w", default=".", help="The path to the colcon workspace (default: \".\")")
    list_repos_parser.set_defaults(func=list_repos_command)

    # Profile subcommand with its own subcommands
    profile_parser = subparsers.add_parser("profile", help="Manage config profiles for a colcon workspace.")
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command")
    
    add_parser = profile_subparsers.add_parser("add", help="Add a profile")
    add_parser.add_argument("name", type=str, help="The new profile name.")
    add_parser.add_argument("--force", "-f", action="store_true", help="Overwrite an existing profile.")
    add_parser.add_argument("--copy", metavar="BASE_PROFILE", type=str, help="Copy the settings from an existing profile. (default: None)")
    add_parser.add_argument("--copy-active", action="store_true", help="Copy the settings from the active profile.")
    add_parser.set_defaults(func=profile_add)

    remove_parser = profile_subparsers.add_parser("remove", help="Remove a profile")
    remove_parser.add_argument("name", type=str, nargs="*", help="One or more profile names to remove.")
    remove_parser.set_defaults(func=profile_remove)

    set_parser = profile_subparsers.add_parser("set", help="Set the active profile")
    set_parser.add_argument("name", type=str, help="The parser to activate.")
    set_parser.set_defaults(func=profile_set)

    rename_parser = profile_subparsers.add_parser("rename", help="Rename a profile")
    rename_parser.add_argument("current_name", type=str, help="The current name of the profile to be renamed.")
    rename_parser.add_argument("new_name", type=str, help="The new name for the profile.")
    rename_parser.add_argument("--force", "-f", action="store_true", help="Overwrite an existing profile.")
    rename_parser.set_defaults(func=profile_rename)
    
    test_parser = subparsers.add_parser("test", help="Tests a colcon workspace.")
    test_parser.add_argument("--workspace", "-w", default=".", help="The path to the colcon workspace (default: \".\")")
    test_parser.add_argument("--profile", default="default", help="The name of a config profile to use (default: 'default')")

    test_packages_group = test_parser.add_argument_group('Packages', 'Clean workspace subdirectories for the selected profile.')
    test_packages_group.add_argument("pkgs", metavar="PKGNAME", nargs='*', type=str, help='Explicilty specify a list of specific packages to test.')
    test_packages_group.add_argument("--this", action="store_true", help="Clean the package containing the current working directory from the build and install space.")
    test_packages_group.add_argument("--no-deps", action="store_true", help="Only build specified packages, not their dependencies.")

    test_config_group = test_parser.add_argument_group('Config', "Parameters for the underlying build system.")
    test_config_group.add_argument("--colcon-build-args", metavar='ARG', dest='colcon_build_args', 
                                    nargs="+", required=False, type=str, default=None, help="Additional arguments for colcon")

    test_parser.set_defaults(func=test_command)

    sysargs = sys.argv[1:]
    pre_verb_args = []
    verb = None
    post_verb_args = []
    for index, arg in enumerate(sysargs):
        if not arg.startswith('-'):
            verb = arg
            post_verb_args = sysargs[index + 1:]
            break
        if arg in ['-h', '--help', '--version']:
            args = parser.parse_args(sysargs)
            if args.version:
                version = pkg_resources.get_distribution('hatch_colcon').version
                year = date.today().year
                if year > 2025:
                    year = f'2025-{year}'
                print(f"hatch_colcon {version} (C) {year} Hatchbed LLC")
                print("hatch_colcon is released under the BSD 3-Clause License (https://opensource.org/license/bsd-3-clause)")
                print('---')
                print('Using Python {}'.format(''.join(sys.version.split('\n'))))
                sys.exit(0)
        pre_verb_args.append(arg)

    if verb is None:
        parser.print_help()
        sys.exit("Error: No verb provided.")
    elif verb not in ['build', 'clean', 'config', 'init', 'list', 'profile', 'test']:
        parser.print_help()
        sys.exit("Error: Unknown verb '{0}' provided.".format(verb))

    post_verb_args, colcon_build_args = get_colcon_build_args(verb, post_verb_args)
    processed_args = pre_verb_args + [verb] + post_verb_args

    args = parser.parse_args(processed_args)
    if colcon_build_args:
        setattr(args, "colcon_build_args", colcon_build_args)
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as exp:
        pass
