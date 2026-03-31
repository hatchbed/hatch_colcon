import argparse
import importlib.metadata
import sys
from datetime import date

from .common import get_colcon_build_args
from . import build, clean, completion, config, init, list as list_cmd, profile, test


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

    build.register(subparsers)
    clean.register(subparsers)
    completion.register(subparsers)
    config.register(subparsers)
    init.register(subparsers)
    list_cmd.register(subparsers)
    profile.register(subparsers)
    test.register(subparsers)

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
