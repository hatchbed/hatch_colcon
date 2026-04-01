_BASH_COMPLETION_SCRIPT = """\
# Bash completion for hatchy (https://github.com/hatchbed/hatch_colcon)

_hatchy_packages() {
    local ws="${1:-.}"
    if [[ -d "$ws/src" ]]; then
        find "$ws/src" -name "package.xml" -exec dirname {} \\; 2>/dev/null \\
            | xargs -I{} basename {} 2>/dev/null
    fi
}

_hatchy_get_workspace() {
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

_hatchy() {
    local cur prev words cword
    _init_completion || return

    local workspace
    workspace="$(_hatchy_get_workspace "${words[@]}")"

    # Determine subcommand and optional sub-subcommand
    local subcommand="" subsubcommand=""
    local i
    for ((i = 1; i < cword; i++)); do
        [[ "${words[i]}" == -* ]] && continue
        if [[ -z "$subcommand" ]]; then
            subcommand="${words[i]}"
        elif [[ "$subcommand" == "list" ]]; then
            subsubcommand="${words[i]}"
            break
        fi
    done

    # Top level
    if [[ -z "$subcommand" ]]; then
        COMPREPLY=($(compgen -W \\
            "--version --help build clean completion config init list test" \\
            -- "$cur"))
        return
    fi

    if [[ "$prev" == "--workspace" || "$prev" == "-w" ]]; then
        _filedir -d
        return
    fi

    case "$subcommand" in
        build)
            if [[ -n "$cur" && "$cur" != -* ]]; then
                COMPREPLY=($(compgen -W "$(_hatchy_packages "$workspace")" -- "$cur"))
            else
                COMPREPLY=($(compgen -W "
                    --workspace -w --this --no-deps
                    --colcon-build-args --nice -n --help
                " -- "$cur"))
            fi
            ;;
        clean)
            if [[ -n "$cur" && "$cur" != -* ]]; then
                COMPREPLY=($(compgen -W "$(_hatchy_packages "$workspace")" -- "$cur"))
            else
                COMPREPLY=($(compgen -W "
                    --workspace -w
                    --yes -y
                    --build-space --build -b
                    --install-space --install -i
                    --test-result-space --test -t
                    --log-space --logs -l
                    --this --dependents --dep --help
                " -- "$cur"))
            fi
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
                --workspace -w
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
        test)
            if [[ -n "$cur" && "$cur" != -* ]]; then
                COMPREPLY=($(compgen -W "$(_hatchy_packages "$workspace")" -- "$cur"))
            else
                COMPREPLY=($(compgen -W "
                    --workspace -w --this --no-deps
                    --colcon-build-args --verbose -v
                    --results-only -r --no-color --help
                " -- "$cur"))
            fi
            ;;
    esac
}

complete -F _hatchy hatchy
"""


def register(subparsers):
    parser = subparsers.add_parser(
        "completion", help="Print the bash completion script to stdout.")
    parser.set_defaults(func=completion_command)


def completion_command(args):
    print(_BASH_COMPLETION_SCRIPT, end="")
