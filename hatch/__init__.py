#!/usr/bin/env python3

import argparse
import importlib.metadata
import sys
from datetime import date

from .build import build_command
from .clean import clean_command
from .completion import completion_command
from .config import config_command
from .common import get_colcon_build_args
from .init import init_command
from .list import list_packages_command, list_repos_command
from .profile import profile_add, profile_remove, profile_rename, profile_set
from .test import test_command


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

    subparsers = parser.add_subparsers(
        dest="command", title="hatch command",
        description="Call `hatch VERB -h` for help on each verb listed below:",
        metavar="")

    # build
    builder_parser = subparsers.add_parser("build", help="Builds a colcon workspace.")
    builder_parser.add_argument("--workspace", "-w", default=".",
                                help="The path to the colcon workspace (default: \".\")")
    builder_parser.add_argument("--profile", default="default",
                                help="The name of a config profile to use (default: 'default')")
    build_packages_group = builder_parser.add_argument_group(
        'Packages', 'Clean workspace subdirectories for the selected profile.')
    build_packages_group.add_argument(
        "pkgs", metavar="PKGNAME", nargs='*', type=str,
        help='Explicilty specify a list of specific packages to build.')
    build_packages_group.add_argument(
        "--this", action="store_true",
        help="Build the package containing the current working directory.")
    build_packages_group.add_argument(
        "--no-deps", action="store_true",
        help="Only build specified packages, not their dependencies.")
    build_config_group = builder_parser.add_argument_group(
        'Config', "Parameters for the underlying build system.")
    build_config_group.add_argument(
        "--colcon-build-args", metavar='ARG', dest='colcon_build_args',
        nargs="+", required=False, type=str, default=None,
        help="Additional arguments for colcon")
    build_config_group.add_argument(
        "--nice", "-n", type=int, help="CPU niceness for build commands. (default: 0)")
    builder_parser.set_defaults(func=build_command)

    # clean
    clean_parser = subparsers.add_parser("clean", help="Deletes various products of the build verb.")
    clean_parser.add_argument("--workspace", "-w", default=".",
                              help="The path to the colcon workspace (default: \".\")")
    clean_parser.add_argument("--profile", default="default",
                              help="The name of a config profile to use (default: 'default')")
    clean_parser.add_argument("--yes", "-y", action="store_true",
                              help="Assume \"yes\" to all interactive checks.")
    clean_parser.add_argument(
        "--all-profiles", "-a", action="store_true",
        help="Apply the specified clean operation for all profiles in this workspace.")
    clean_parser.add_argument(
        "--deinit", action="store_true",
        help="De-initialize the workspace, delete all build profiles and configuration. "
             "This will also clean subdirectories for all profiles in the workspace.")
    clean_spaces_group = clean_parser.add_argument_group(
        'Spaces', 'Clean workspace subdirectories for the selected profile.')
    clean_spaces_group.add_argument("--build-space", "--build", "-b", action="store_true",
                                    help="Remove the entire build space")
    clean_spaces_group.add_argument("--install-space", "--install", "-i", action="store_true",
                                    help="Remove the entire install space")
    clean_spaces_group.add_argument("--test-result-space", "--test", "-t", action="store_true",
                                    help="Remove the entire test result space")
    clean_spaces_group.add_argument("--log-space", "--logs", "-l", action="store_true",
                                    help="Remove the entire log space")
    clean_packages_group = clean_parser.add_argument_group(
        'Packages', 'Clean workspace subdirectories for the selected profile.')
    clean_packages_group.add_argument(
        "pkgs", metavar="PKGNAME", nargs='*', type=str,
        help='Explicilty specify a list of specific packages to clean from the build, '
             'devel, and install space.')
    clean_packages_group.add_argument(
        "--this", action="store_true",
        help="Clean the package containing the current working directory from the build "
             "and install space.")
    clean_packages_group.add_argument(
        "--dependents", "--dep", action="store_true",
        help="Clean the packages which depend on the packages to be cleaned.")
    clean_parser.set_defaults(func=clean_command)

    # completion
    completion_parser = subparsers.add_parser(
        "completion", help="Print the bash completion script to stdout.")
    completion_parser.set_defaults(func=completion_command)

    # config
    config_parser = subparsers.add_parser("config",
                                          help="Configures a colcon workspace's context.")
    config_parser.add_argument("--workspace", "-w", default=".",
                               help="The path to the colcon workspace (default: \".\")")
    config_parser.add_argument("--profile", default="default",
                               help="The name of a config profile to use (default: 'default')")
    config_behavior_group = config_parser.add_argument_group(
        'Behavior', 'Options affecting argument handling.')
    config_behavior_group.add_argument("--append-args", "-a", action="store_true",
                                       help="Append elements to list-type arguments")
    config_behavior_group.add_argument("--remove-args", "-r", action="store_true",
                                       help="Remove elements from list-type arguments")
    config_context_group = config_parser.add_argument_group(
        'Workspace Context', 'Options affecting the context of the workspace.')
    config_context_group.add_argument("--extend", "-e",
                                      help="Extend the result-space of another colcon workspace")
    config_context_group.add_argument("--no-extend", action="store_true",
                                      help="Unset the explicit extension of another workspace")
    config_spaces_group = config_parser.add_argument_group(
        'Spaces', 'Location of parts of the colcon workspace.')
    config_spaces_group.add_argument("--build-space", "--build", "-b",
                                     help="Path to the build space")
    config_spaces_group.add_argument("--default-build-space", action="store_true",
                                     help="Use the default build space ('build')")
    config_spaces_group.add_argument("--install-space", "--install", "-i",
                                     help="Path to the install space")
    config_spaces_group.add_argument("--default-install-space", action="store_true",
                                     help="Use the default install space ('install')")
    config_spaces_group.add_argument("--test-result-space", "--test", "-t",
                                     help="Path to the test result space")
    config_spaces_group.add_argument("--default-test-result-space", action="store_true",
                                     help="Use the default test result space ('test_results')")
    config_spaces_group.add_argument("--space-suffix", "-x",
                                     help="Suffix for build, test results, and install space")
    config_build_group = config_parser.add_argument_group(
        'Build Options', 'Options for configuring the way packages are built.')
    config_build_group.add_argument("--no-colcon-build-args", action="store_true",
                                    help="Pass no additional arguments to colcon")
    config_build_group.add_argument(
        "--colcon-build-args", metavar='ARG', dest='colcon_build_args',
        nargs="+", required=False, type=str, default=None,
        help="Additional arguments for colcon")
    config_build_group.add_argument("--nice", "-n", type=int,
                                    help="CPU niceness for build commands. (default: 0)")
    config_parser.set_defaults(func=config_command)

    # init
    init_parser = subparsers.add_parser("init",
                                        help="Initializes a given folder as a colcon workspace.")
    init_parser.add_argument("--workspace", "-w", default=".",
                             help="The path to the colcon workspace (default: \".\")")
    init_parser.set_defaults(func=init_command)

    # list
    list_parser = subparsers.add_parser(
        "list", help="Lists colcon packages in the workspace or other arbitrary folders.")
    list_subparsers = list_parser.add_subparsers(dest="list_command")
    list_packages_parser = list_subparsers.add_parser("packages", help="List packages in workspace.")
    list_packages_parser.add_argument("--workspace", "-w", default=".",
                                      help="The path to the colcon workspace (default: \".\")")
    list_packages_parser.set_defaults(func=list_packages_command)
    list_repos_parser = list_subparsers.add_parser("repos", help="List repos in workspace.")
    list_repos_parser.add_argument("--workspace", "-w", default=".",
                                   help="The path to the colcon workspace (default: \".\")")
    list_repos_parser.set_defaults(func=list_repos_command)

    # profile
    profile_parser = subparsers.add_parser("profile",
                                           help="Manage config profiles for a colcon workspace.")
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command")
    add_parser = profile_subparsers.add_parser("add", help="Add a profile")
    add_parser.add_argument("name", type=str, help="The new profile name.")
    add_parser.add_argument("--force", "-f", action="store_true",
                            help="Overwrite an existing profile.")
    add_parser.add_argument("--copy", metavar="BASE_PROFILE", type=str,
                            help="Copy the settings from an existing profile. (default: None)")
    add_parser.add_argument("--copy-active", action="store_true",
                            help="Copy the settings from the active profile.")
    add_parser.set_defaults(func=profile_add)
    remove_parser = profile_subparsers.add_parser("remove", help="Remove a profile")
    remove_parser.add_argument("name", type=str, nargs="*",
                               help="One or more profile names to remove.")
    remove_parser.set_defaults(func=profile_remove)
    set_parser = profile_subparsers.add_parser("set", help="Set the active profile")
    set_parser.add_argument("name", type=str, help="The profile to activate.")
    set_parser.set_defaults(func=profile_set)
    rename_parser = profile_subparsers.add_parser("rename", help="Rename a profile")
    rename_parser.add_argument("current_name", type=str,
                               help="The current name of the profile to be renamed.")
    rename_parser.add_argument("new_name", type=str, help="The new name for the profile.")
    rename_parser.add_argument("--force", "-f", action="store_true",
                               help="Overwrite an existing profile.")
    rename_parser.set_defaults(func=profile_rename)

    # test
    test_parser = subparsers.add_parser("test", help="Tests a colcon workspace.")
    test_parser.add_argument("--workspace", "-w", default=".",
                             help="The path to the colcon workspace (default: \".\")")
    test_parser.add_argument("--profile", default="default",
                             help="The name of a config profile to use (default: 'default')")
    test_packages_group = test_parser.add_argument_group('Packages', 'Select packages to test.')
    test_packages_group.add_argument(
        "pkgs", metavar="PKGNAME", nargs='*', type=str,
        help='Explicitly specify a list of specific packages to test.')
    test_packages_group.add_argument(
        "--this", action="store_true",
        help="Test the package containing the current working directory.")
    test_packages_group.add_argument(
        "--no-deps", action="store_true",
        help="Only test specified packages, not their dependencies.")
    test_config_group = test_parser.add_argument_group(
        'Config', "Parameters for the underlying build system.")
    test_config_group.add_argument(
        "--colcon-build-args", metavar='ARG', dest='colcon_build_args',
        nargs="+", required=False, type=str, default=None,
        help="Additional arguments for colcon")
    test_config_group.add_argument("--verbose", "-v", action="store_true",
                                   help="Show the status of every individual test case.")
    test_config_group.add_argument("--results-only", "-r", action="store_true",
                                   help="Show results from the last test run without re-running.")
    test_config_group.add_argument("--no-color", action="store_true",
                                   help="Disable colored output.")
    test_parser.set_defaults(func=test_command)

    # parse
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
                print("hatch_colcon is released under the BSD 3-Clause License "
                      "(https://opensource.org/license/bsd-3-clause)")
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
    except KeyboardInterrupt:
        pass
