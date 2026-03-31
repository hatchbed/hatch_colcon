import os
import subprocess
import sys

from .common import get_workspace_dir, parse_package_name


def register(subparsers):
    parser = subparsers.add_parser(
        "list", help="Lists colcon packages in the workspace or other arbitrary folders.")
    list_subparsers = parser.add_subparsers(dest="list_command")

    packages_parser = list_subparsers.add_parser("packages", help="List packages in workspace.")
    packages_parser.add_argument("--workspace", "-w", default=".",
                                 help="The path to the colcon workspace (default: \".\")")
    packages_parser.set_defaults(func=list_packages_command)

    repos_parser = list_subparsers.add_parser("repos", help="List repos in workspace.")
    repos_parser.add_argument("--workspace", "-w", default=".",
                              help="The path to the colcon workspace (default: \".\")")
    repos_parser.set_defaults(func=list_repos_command)


_VCS_MARKERS = {
    ".git": "git",
    ".hg":  "hg",
    ".svn": "svn",
    ".bzr": "bzr",
}


def find_packages(src_dir):
    """Walk src_dir and return a sorted list of (name, rel_path) for each package.xml found."""
    workspace = os.path.dirname(src_dir)
    packages = []
    for dirpath, dirnames, filenames in os.walk(src_dir):
        if "package.xml" in filenames:
            name = parse_package_name(os.path.join(dirpath, "package.xml"))
            if name:
                rel = os.path.relpath(dirpath, workspace)
                packages.append((name, rel))
    return sorted(packages, key=lambda p: p[0])


def find_repos(src_dir):
    """Walk src_dir and return a sorted list of repo dicts, not descending into nested repos."""
    workspace = os.path.dirname(src_dir)
    repos = []

    def _walk(directory):
        try:
            entries = list(os.scandir(directory))
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


def _resolve_workspace(args):
    workspace = get_workspace_dir(os.path.abspath(args.workspace))
    if workspace is None:
        print(f"Error: Could not find a hatch workspace from '{args.workspace}'.")
        sys.exit(1)
    src_dir = os.path.join(workspace, "src")
    if not os.path.isdir(src_dir):
        print(f"Error: No 'src' directory found in workspace '{workspace}'.")
        sys.exit(1)
    return workspace, src_dir


def list_packages_command(args):
    workspace, src_dir = _resolve_workspace(args)
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
    workspace, src_dir = _resolve_workspace(args)
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
