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
        COMPREPLY=($(compgen -W \\
            "--version --help build clean completion config init list profile test" \\
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
                    COMPREPLY=($(compgen -W \\
                        "--help $(_hatch_colcon_profiles "$workspace")" -- "$cur"))
                    ;;
                rename)
                    COMPREPLY=($(compgen -W \\
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
