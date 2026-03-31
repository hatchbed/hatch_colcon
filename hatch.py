#!/usr/bin/env python3

import argparse
import shlex
from datetime import date
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import time
import xml.etree.ElementTree as ET
import yaml

# ANSI color codes
_RESET = "\033[0m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD_RED = "\033[1;31m"


_color = True


def clr(text, code):
    """Wrap text in an ANSI color code if stdout is a TTY and color is enabled."""
    if _color and sys.stdout.isatty():
        return f"{code}{text}{_RESET}"
    return text


def remove_duplicates(lst):
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]


def delete_matching_dirs(root_dir, names_to_delete):
    root_path = Path(root_dir)
    for subdir in root_path.rglob('*'):
        if subdir.is_dir() and subdir.name in names_to_delete:
            shutil.rmtree(subdir)


def get_dependent_packages(packages):
    cmd = ["colcon", "list", "-n", "--packages-above"] + packages
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    pkgs = [pkg for pkg in result.stdout.splitlines() if "not found" not in pkg.lower()]
    return pkgs


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


_BASH_COMPLETION_SCRIPT = """\
# Bash completion for hatch_colcon (https://github.com/hatchbed/hatch_colcon)

_hatch_colcon_packages() {
    local ws="${1:-.}"
    if [[ -d "$ws/src" ]]; then
        find "$ws/src" -name "package.xml" -exec dirname {} \\; 2>/dev/null \\
            | xargs -I{} basename {} 2>/dev/null
    fi
}

_hatch_colcon_profiles() {
    local ws="${1:-.}"
    local profiles_dir="$ws/.hatch/profiles"
    if [[ -d "$profiles_dir" ]]; then
        ls "$profiles_dir" 2>/dev/null | grep -v 'profiles.yaml'
    fi
}

_hatch_colcon_get_workspace() {
    local words=("$@")
    local cword="${#words[@]}"
    local ws="."
    local i
    for ((i = 1; i < cword; i++)); do
        if [[ "${words[i]}" == "--workspace" || "${words[i]}" == "-w" ]]; then
            ws="${words[i+1]:-$ws}"
            break
        fi
    done
    echo "$ws"
}

_hatch_colcon() {
    local cur prev words cword
    _init_completion || return

    local workspace
    workspace="$(_hatch_colcon_get_workspace "${words[@]}")"

    # Determine subcommand and optional sub-subcommand
    local subcommand="" subsubcommand=""
    local i
    for ((i = 1; i < cword; i++)); do
        [[ "${words[i]}" == -* ]] && continue
        if [[ -z "$subcommand" ]]; then
            subcommand="${words[i]}"
        elif [[ "$subcommand" == "list" || "$subcommand" == "profile" ]]; then
            subsubcommand="${words[i]}"
            break
        fi
    done

    # Top level
    if [[ -z "$subcommand" ]]; then
        COMPREPLY=($(compgen -W \
            "--version --help build clean completion config init list profile test" \
            -- "$cur"))
        return
    fi

    # Shared: --workspace / --profile completion
    if [[ "$prev" == "--workspace" || "$prev" == "-w" ]]; then
        _filedir -d
        return
    fi
    if [[ "$prev" == "--profile" ]]; then
        COMPREPLY=($(compgen -W "$(_hatch_colcon_profiles "$workspace")" -- "$cur"))
        return
    fi

    case "$subcommand" in
        build)
            COMPREPLY=($(compgen -W "
                --workspace -w --profile --this --no-deps
                --colcon-build-args --nice -n --help
                $(_hatch_colcon_packages "$workspace")
            " -- "$cur"))
            ;;
        clean)
            COMPREPLY=($(compgen -W "
                --workspace -w --profile
                --yes -y --all-profiles -a --deinit
                --build-space --build -b
                --install-space --install -i
                --test-result-space --test -t
                --log-space --logs -l
                --this --dependents --dep --help
                $(_hatch_colcon_packages "$workspace")
            " -- "$cur"))
            ;;
        completion)
            COMPREPLY=($(compgen -W "--help" -- "$cur"))
            ;;
        config)
            if [[ "$prev" == "--extend" || "$prev" == "-e" ]]; then
                _filedir -d
                return
            fi
            COMPREPLY=($(compgen -W "
                --workspace -w --profile
                --append-args -a --remove-args -r
                --extend -e --no-extend
                --build-space --build -b --default-build-space
                --install-space --install -i --default-install-space
                --test-result-space --test -t --default-test-result-space
                --space-suffix -x
                --no-colcon-build-args --colcon-build-args
                --nice -n --help
            " -- "$cur"))
            ;;
        init)
            COMPREPLY=($(compgen -W "--workspace -w --help" -- "$cur"))
            ;;
        list)
            if [[ -z "$subsubcommand" ]]; then
                COMPREPLY=($(compgen -W "--help packages repos" -- "$cur"))
            else
                COMPREPLY=($(compgen -W "--workspace -w --help" -- "$cur"))
            fi
            ;;
        profile)
            if [[ -z "$subsubcommand" ]]; then
                COMPREPLY=($(compgen -W "--help add remove set rename" -- "$cur"))
                return
            fi
            case "$subsubcommand" in
                add)
                    if [[ "$prev" == "--copy" ]]; then
                        COMPREPLY=($(compgen -W "$(_hatch_colcon_profiles "$workspace")" -- "$cur"))
                        return
                    fi
                    COMPREPLY=($(compgen -W "--force -f --copy --copy-active --help" -- "$cur"))
                    ;;
                remove|set)
                    COMPREPLY=($(compgen -W \
                        "--help $(_hatch_colcon_profiles "$workspace")" -- "$cur"))
                    ;;
                rename)
                    COMPREPLY=($(compgen -W \
                        "--force -f --help $(_hatch_colcon_profiles "$workspace")" -- "$cur"))
                    ;;
            esac
            ;;
        test)
            COMPREPLY=($(compgen -W "
                --workspace -w --profile --this --no-deps
                --colcon-build-args --verbose -v
                --results-only -r --no-color --help
                $(_hatch_colcon_packages "$workspace")
            " -- "$cur"))
            ;;
    esac
}

complete -F _hatch_colcon hatch
"""


def completion_command(args):
    print(_BASH_COMPLETION_SCRIPT, end="")


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
        "install_space": "install",
        "test_result_space": "test_results"
    }
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config_content.update(yaml.safe_load(f))

    # Build space
    build_space = config_content.get("build_space", "build")
    if not build_space:
        build_space = "build"

    # Install space
    install_space = config_content.get("install_space", "install")
    if not install_space:
        install_space = "install"

    # Test results space
    test_result_space = config_content.get("test_result_space", "test_results")
    if not test_result_space:
        test_result_space = "test_results"

    # Clean targets
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

    target_paths = []
    for target in targets:
        target_path = os.path.join(workspace, target)
        if os.path.isdir(target_path):
            target_paths.append(target_path)

    if len(target_paths) == 0:
        print("Nothing to clean.")
        return

    # Clean packages
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
        targets_str = "\n".join(['    ' + target for target in target_paths])
        print(f"{targets_str}")
    else:
        print("Cleaning:")
        targets_str = "\n".join(['    ' + target for target in target_paths])
        print(f"{targets_str}")

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


def get_xunit_path_from_cmdline(cmdline):
    """Extract the xunit result file path from a run_test.py FullCommandLine."""
    try:
        tokens = shlex.split(cmdline)
        for i, token in enumerate(tokens):
            if 'run_test.py' in token and i + 1 < len(tokens):
                return tokens[i + 1]
    except Exception:
        pass
    return None


def parse_xunit_results(xunit_path):
    """Parse a JUnit/xunit/GTest XML file.

    Returns (total, passed, skipped, failures, errors, failed_names, all_cases) or None on error.
    all_cases is a list of (name, status) where status is 'passed', 'failed', 'skipped', or 'error'.
    """
    try:
        tree = ET.parse(xunit_path)
        root = tree.getroot()
        total = failures = errors = skipped = 0
        failed_names = []
        all_cases = []

        suites = root.findall('testsuite') if root.tag == 'testsuites' else [root]
        for suite in suites:
            total += int(suite.get('tests', 0))
            failures += int(suite.get('failures', 0))
            errors += int(suite.get('errors', 0))
            skipped += int(suite.get('skipped', suite.get('disabled', 0)))
            for tc in suite.findall('testcase'):
                tc_name = tc.get('name', 'unknown')
                detail = None
                fail_el = tc.find('failure')
                err_el = tc.find('error')
                if fail_el is not None:
                    status = 'failed'
                    failed_names.append(tc_name)
                    detail = fail_el.get('message') or (fail_el.text or '').strip()
                elif err_el is not None:
                    status = 'error'
                    failed_names.append(tc_name)
                    detail = err_el.get('message') or (err_el.text or '').strip()
                elif tc.find('skipped') is not None or tc.get('status') == 'notrun':
                    status = 'skipped'
                else:
                    status = 'passed'
                all_cases.append((tc_name, status, detail))

        passed = total - failures - errors - skipped
        return total, passed, skipped, failures, errors, failed_names, all_cases
    except Exception:
        return None


def get_latest_ctest_xml(pkg_build_dir):
    """Return the path to the most recent Test.xml for a package, or None."""
    testing_dir = os.path.join(pkg_build_dir, 'Testing')
    if not os.path.isdir(testing_dir):
        return None
    timestamps = sorted([
        d for d in os.listdir(testing_dir)
        if os.path.isdir(os.path.join(testing_dir, d)) and d != 'Temporary'
    ])
    if not timestamps:
        return None
    xml_path = os.path.join(testing_dir, timestamps[-1], 'Test.xml')
    return xml_path if os.path.isfile(xml_path) else None


def print_test_results(workspace, build_space, verbose=False, packages=None):
    """Parse CTest XML files and print a nested test result summary.

    Returns 0 if all tests passed, 1 if any failed.
    If packages is provided, only results for those packages are shown.
    """
    build_dir = os.path.join(workspace, build_space)
    if not os.path.isdir(build_dir):
        print("No build directory found, no test results to show.")
        return 1

    all_pkgs = sorted([
        d for d in os.listdir(build_dir)
        if os.path.isdir(os.path.join(build_dir, d, 'Testing'))
    ])

    if packages:
        all_pkgs = [p for p in all_pkgs if p in packages]

    if not all_pkgs:
        print("No test results found.")
        return 0

    packages = all_pkgs

    total_suites = total_suites_passed = 0
    total_tests = total_passed = total_skipped = total_failed = 0
    any_failure = False

    print()
    print("-" * 70)

    for pkg in packages:
        ctest_xml = get_latest_ctest_xml(os.path.join(build_dir, pkg))
        if ctest_xml is None:
            continue
        try:
            root = ET.parse(ctest_xml).getroot()
        except Exception:
            continue

        test_entries = root.findall('.//Testing/Test')
        if not test_entries:
            continue

        suite_data = []
        pkg_tests = pkg_passed = pkg_skipped = pkg_failed_tests = pkg_suites_passed = 0
        pkg_failed = False

        for entry in test_entries:
            name = entry.findtext('Name', '')
            suite_ok = entry.get('Status') == 'passed'

            exec_time = None
            for nm in entry.findall('.//NamedMeasurement'):
                if nm.get('name') == 'Execution Time':
                    try:
                        exec_time = float(nm.findtext('Value', '0'))
                    except ValueError:
                        pass

            labels = [lbl.text for lbl in entry.findall('.//Label') if lbl.text]
            label = labels[0] if labels else ''

            xunit_path = get_xunit_path_from_cmdline(entry.findtext('FullCommandLine', ''))
            xunit = None
            if xunit_path and os.path.isfile(xunit_path):
                xunit = parse_xunit_results(xunit_path)

            if xunit:
                n_total, n_passed, n_skipped, n_failures, n_errors, _, _ = xunit
                pkg_tests += n_total
                pkg_passed += n_passed
                pkg_skipped += n_skipped
                pkg_failed_tests += n_failures + n_errors
                if n_failures or n_errors:
                    suite_ok = False

            if suite_ok:
                pkg_suites_passed += 1
            else:
                pkg_failed = True

            suite_data.append((name, label, exec_time, xunit, suite_ok))

        if pkg_failed:
            any_failure = True
        n_suites = len(test_entries)
        total_suites += n_suites
        total_suites_passed += pkg_suites_passed
        total_tests += pkg_tests
        total_passed += pkg_passed
        total_skipped += pkg_skipped
        total_failed += pkg_failed_tests

        # Package header line
        if pkg_tests > 0:
            parts = [clr(f"{pkg_passed} passed", _GREEN)]
            if pkg_skipped:
                parts.append(clr(f"{pkg_skipped} skipped", _YELLOW))
            if pkg_failed_tests:
                parts.append(clr(f"{pkg_failed_tests} failed", _BOLD_RED))
            print(f"{pkg}: {pkg_suites_passed}/{n_suites} suites passed  ({', '.join(parts)})")
        else:
            print(f"{pkg}: {pkg_suites_passed}/{n_suites} suites passed")

        # Per-suite lines
        name_w = max(len(s[0]) for s in suite_data)
        label_w = max((len(f" [{s[1]}]") if s[1] else 0) for s in suite_data)

        # Pre-compute counts strings and their visible lengths for time column alignment
        suite_counts = []
        for name, label, exec_time, xunit, suite_ok in suite_data:
            if xunit:
                n_total, n_passed, n_skipped, n_failures, n_errors, failed_names, all_cases = xunit
                plain_parts = []
                counts = []
                if n_passed:
                    plain_parts.append(f"{n_passed} passed")
                    counts.append(clr(f"{n_passed} passed", _GREEN))
                if n_skipped:
                    plain_parts.append(f"{n_skipped} skipped")
                    counts.append(clr(f"{n_skipped} skipped", _YELLOW))
                if n_failures:
                    plain_parts.append(f"{n_failures} failed")
                    counts.append(clr(f"{n_failures} failed", _BOLD_RED))
                if n_errors:
                    plain_parts.append(f"{n_errors} errors")
                    counts.append(clr(f"{n_errors} errors", _BOLD_RED))
                counts_str = ", ".join(counts) if counts else "0 tests"
                counts_vis = len(", ".join(plain_parts)) if plain_parts else len("0 tests")
            else:
                counts_str = clr("passed", _GREEN) if suite_ok else clr("FAILED", _BOLD_RED)
                counts_vis = len("passed" if suite_ok else "FAILED")
            suite_counts.append((xunit, counts_str, counts_vis))

        counts_w = max(cv for _, _, cv in suite_counts)

        for (name, label, exec_time, xunit, suite_ok), (xunit2, counts_str, counts_vis) in \
                zip(suite_data, suite_counts):
            tag = clr("[ ok ]", _GREEN) if suite_ok else clr("[FAIL]", _BOLD_RED)
            label_str = f" [{label}]" if label else ""
            time_str = f"  ({exec_time:.2f}s)" if exec_time is not None else ""
            padding = " " * (counts_w - counts_vis)

            if xunit:
                n_total, n_passed, n_skipped, n_failures, n_errors, failed_names, all_cases = xunit
                print(f"  {tag} {name:<{name_w}}{label_str:<{label_w}}  {counts_str}{padding}{time_str}")
                if verbose:
                    for tc_name, tc_status, detail in all_cases:
                        tc_tag = clr("[ ok ]", _GREEN) if tc_status == 'passed' else \
                                 clr("[SKIP]", _YELLOW) if tc_status == 'skipped' else \
                                 clr("[FAIL]", _BOLD_RED)
                        print(f"       {tc_tag} {tc_name}")
                        if detail and tc_status in ('failed', 'error'):
                            for line in detail.splitlines():
                                print(f"              {clr(line, _RED)}")
                elif failed_names:
                    for tc_name, tc_status, detail in all_cases:
                        if tc_status not in ('failed', 'error'):
                            continue
                        print(f"         FAILED: {tc_name}")
                        if detail:
                            for line in detail.splitlines():
                                print(f"                {clr(line, _RED)}")
            else:
                print(f"  {tag} {name:<{name_w}}{label_str:<{label_w}}  {counts_str}{padding}{time_str}")

        print()

    print("-" * 70)
    suite_str = f"{total_suites_passed}/{total_suites} suites"
    summary_status = clr("FAILED", _BOLD_RED) if any_failure else clr("passed", _GREEN)
    if total_tests > 0:
        test_parts = [clr(f"{total_passed} passed", _GREEN)]
        if total_skipped:
            test_parts.append(clr(f"{total_skipped} skipped", _YELLOW))
        if total_failed:
            test_parts.append(clr(f"{total_failed} failed", _BOLD_RED))
        print(f"Summary: {suite_str} | {', '.join(test_parts)} -- {summary_status}")
    else:
        print(f"Summary: {suite_str} -- {summary_status}")
    print("-" * 70)

    return 1 if any_failure else 0


def test_command(args):
    if args.no_color:
        global _color
        _color = False

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

    # Build space
    build_space = config_content.get("build_space", "build")
    if not build_space:
        build_space = "build"

    if args.results_only:
        packages = args.pkgs
        if args.this:
            current_package = get_package(args.workspace)
            if current_package:
                packages.append(current_package)
        result_code = print_test_results(
            workspace, build_space, verbose=args.verbose,
            packages=packages if packages else None)
        sys.exit(result_code)

    colcon_cmd = ["colcon", "test"]
    colcon_cmd += ['--build-base', build_space]

    # Test results space
    test_result_space = config_content.get("test_result_space", "test_results")
    if not test_result_space:
        test_result_space = "test_results"
    colcon_cmd += ['--test-result-base', test_result_space]

    # Only pass explicitly-provided CLI args — the profile's colcon_build_args are
    # build-specific (e.g. --cmake-args) and not valid for colcon test.
    if args.colcon_build_args:
        colcon_cmd += args.colcon_build_args

    # Nice level
    nice = config_content.get("nice", 0)
    if nice is None:
        nice = 0

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
    extend_script = None
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
    )

    while process.poll() is None:
        subprocess.run(
            f"renice -n {nice} -p $(pgrep -g $(ps -o pgid= -p {process.pid}))",
            shell=True,
            executable="/bin/bash",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        time.sleep(1)

    test_returncode = process.returncode

    result_code = print_test_results(
        workspace, build_space, verbose=args.verbose,
        packages=packages if packages else None)
    sys.exit(max(test_returncode, result_code))

def find_packages(src_dir):
    """Walk src_dir and return a sorted list of (name, rel_path) for each package.xml found."""
    packages = []
    for dirpath, dirnames, filenames in os.walk(src_dir):
        if "package.xml" in filenames:
            name = parse_package_name(os.path.join(dirpath, "package.xml"))
            if name:
                rel = os.path.relpath(dirpath, os.path.dirname(src_dir))
                packages.append((name, rel))
    return sorted(packages, key=lambda p: p[0])


_VCS_MARKERS = {
    ".git": "git",
    ".hg":  "hg",
    ".svn": "svn",
    ".bzr": "bzr",
}


def find_repos(src_dir):
    """Walk src_dir and return a sorted list of repo dicts, not descending into nested repos."""
    repos = []
    workspace = os.path.dirname(src_dir)

    def _walk(directory):
        try:
            entries = os.scandir(directory)
        except PermissionError:
            return
        subdirs = []
        vcs_type = None
        for entry in entries:
            if entry.is_dir(follow_symlinks=False) and entry.name in _VCS_MARKERS:
                vcs_type = _VCS_MARKERS[entry.name]
            elif entry.is_dir(follow_symlinks=False):
                subdirs.append(entry.path)
        if vcs_type:
            info = {"path": os.path.relpath(directory, workspace), "type": vcs_type}
            if vcs_type == "git":
                url = subprocess.run(
                    ["git", "-C", directory, "remote", "get-url", "origin"],
                    capture_output=True, text=True).stdout.strip()
                branch = subprocess.run(
                    ["git", "-C", directory, "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True).stdout.strip()
                info["url"] = url or ""
                info["version"] = branch or ""
            repos.append(info)
        else:
            for subdir in subdirs:
                _walk(subdir)

    _walk(src_dir)
    return sorted(repos, key=lambda r: r["path"])


def list_packages_command(args):
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

    src_dir = os.path.join(workspace, "src")

    if not os.path.isdir(src_dir):
        print(f"Error: No 'src' directory found in workspace '{workspace}'.")
        sys.exit(1)

    packages = find_packages(src_dir)
    if not packages:
        print("No packages found.")
        return

    name_width = max(max(len(name) for name, _ in packages), len("name"))
    path_width = max(max(len(p) for _, p in packages), len("path"))
    print(f"{'name':<{name_width}}  path")
    print(f"{'-' * name_width}  {'-' * path_width}")
    for name, rel_path in packages:
        print(f"{name:<{name_width}}  {rel_path}")


def list_repos_command(args):
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

    src_dir = os.path.join(workspace, "src")

    if not os.path.isdir(src_dir):
        print(f"Error: No 'src' directory found in workspace '{workspace}'.")
        sys.exit(1)

    repos = find_repos(src_dir)
    if not repos:
        print("No repositories found.")
        return

    path_width = max(max(len(r["path"]) for r in repos), len("path"))
    type_width = max(max(len(r["type"]) for r in repos), len("type"))
    url_width = max(max(len(r.get("url", "")) for r in repos), len("url"))
    version_width = max(max(len(r.get("version", "")) for r in repos), len("version"))
    print(f"{'path':<{path_width}}  {'type':<{type_width}}  {'url':<{url_width}}  version")
    print(f"{'-' * path_width}  {'-' * type_width}  {'-' * url_width}  {'-' * version_width}")
    for repo in repos:
        path_col = f"{repo['path']:<{path_width}}"
        type_col = f"{repo['type']:<{type_width}}"
        url_col = f"{repo.get('url', ''):<{url_width}}"
        version = repo.get("version", "")
        print(f"{path_col}  {type_col}  {url_col}  {version}".rstrip())

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

    test_packages_group = test_parser.add_argument_group('Packages', 'Select packages to test.')
    test_packages_group.add_argument("pkgs", metavar="PKGNAME", nargs='*', type=str, help='Explicitly specify a list of specific packages to test.')
    test_packages_group.add_argument("--this", action="store_true", help="Test the package containing the current working directory.")
    test_packages_group.add_argument("--no-deps", action="store_true", help="Only test specified packages, not their dependencies.")

    test_config_group = test_parser.add_argument_group('Config', "Parameters for the underlying build system.")
    test_config_group.add_argument("--colcon-build-args", metavar='ARG', dest='colcon_build_args',
                                    nargs="+", required=False, type=str, default=None,
                                    help="Additional arguments for colcon")
    test_config_group.add_argument("--verbose", "-v", action="store_true",
                                   help="Show the status of every individual test case.")
    test_config_group.add_argument("--results-only", "-r", action="store_true",
                                   help="Show results from the last test run without re-running tests.")
    test_config_group.add_argument("--no-color", action="store_true",
                                   help="Disable colored output.")

    test_parser.set_defaults(func=test_command)

    ## Completion
    completion_parser = subparsers.add_parser(
        "completion",
        help="Print the bash completion script to stdout.")
    completion_parser.set_defaults(func=completion_command)

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
                version = importlib.metadata.version('hatch_colcon')
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
    elif verb not in ['build', 'clean', 'completion', 'config', 'init', 'list', 'profile', 'test']:
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
