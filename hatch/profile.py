def register(subparsers):
    parser = subparsers.add_parser("profile",
                                   help="Manage config profiles for a colcon workspace.")
    profile_subparsers = parser.add_subparsers(dest="profile_command")

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


def profile_add(args):
    pass


def profile_remove(args):
    pass


def profile_set(args):
    pass


def profile_rename(args):
    pass
