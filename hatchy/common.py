import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import yaml
from pathlib import Path

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


def get_colcon_build_args(verb, args):
    if verb not in ['build', 'config', 'test']:
        return args, []

    ordered_splitters = reversed(
        [(i, t) for i, t in enumerate(args) if t in ['--colcon-build-args']])

    head_args = args
    tail_args = []
    colcon_build_args = []
    for index, name in ordered_splitters:
        head_args, colcon_args, tail = split_arguments(head_args, splitter_index=index)
        tail_args.extend(tail)
        colcon_build_args.extend(colcon_args)

    args = head_args + tail_args
    return args, colcon_build_args


def get_workspace_dir(current_dir):
    current_dir = os.path.abspath(current_dir)
    while current_dir != os.path.dirname(current_dir):
        src_path = os.path.join(current_dir, 'src')
        config_path = os.path.join(current_dir, '.hatch', 'config.yaml')
        if os.path.isdir(src_path) and os.path.isfile(config_path):
            return current_dir
        current_dir = os.path.dirname(current_dir)
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
    except Exception:
        return None


def get_package(current_dir):
    current_dir = os.path.abspath(current_dir)
    while current_dir != os.path.dirname(current_dir):
        package_file = os.path.join(current_dir, 'package.xml')
        if os.path.isfile(package_file):
            name = parse_package_name(package_file)
            if name:
                return name
        current_dir = os.path.dirname(current_dir)
    return None



def print_workspace_state(workspace):
    src_dir = os.path.join(workspace, "src")
    config_file = os.path.join(workspace, ".hatch", "config.yaml")

    colcon_build_args = []
    extend_path = None
    build_space = "build"
    install_space = "install"
    test_result_space = "test_results"
    nice = 0

    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
            colcon_build_args = config.get('colcon_build_args', [])
            extend_path = config.get('extend_path', "") or None
            if extend_path is not None and len(extend_path.strip()) == 0:
                extend_path = None
            build_space = config.get("build_space", "build") or "build"
            install_space = config.get("install_space", "install") or "install"
            test_result_space = config.get("test_result_space", "test_results") or "test_results"
            nice = config.get("nice", 0) or 0

    build_dir = os.path.join(workspace, build_space)
    install_dir = os.path.join(workspace, install_space)
    test_results_dir = os.path.join(workspace, test_result_space)
    env_extend_path = os.environ.get("COLCON_PREFIX_PATH", None)

    def _space_status(path):
        return f"{' [exists]' if os.path.exists(path) else '[missing]'} {path}"

    print("-" * 70)
    if extend_path is None:
        if env_extend_path is None:
            print(f"Extending: ")
        else:
            print(f"Extending:             [env] {env_extend_path}")
    else:
        print(f"Extending:                   {extend_path}")
    print(f"Workspace:                   {workspace}")
    print("-" * 70)
    print(f"Build Space:       {_space_status(build_dir)}")
    print(f"Install Space:     {_space_status(install_dir)}")
    print(f"Test Result Space: {_space_status(test_results_dir)}")
    print(f"Source Space:      {' [exists]' if os.path.exists(src_dir) else '[missing]'} "
          f"{src_dir}")
    print("-" * 70)
    print(f"CPU Niceness                 {nice}")
    if not colcon_build_args:
        print(f"Colcon Build Args:           None")
    else:
        print(f"Colcon Build Args:           {colcon_build_args[0]}")
        for arg in colcon_build_args[1:]:
            print(f"                             {arg}")
    print("-" * 70)
