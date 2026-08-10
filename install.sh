#!/usr/bin/env bash
# macOS / Linux: put `kbuba` on the PATH (symlink into the first writable
# standard bin dir). Windows: see README - create a kbuba.cmd shim instead.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)/bin/kbuba"
chmod +x "$SRC"
for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin"; do
    if [ -d "$d" ] && [ -w "$d" ] || [ "$d" = "$HOME/.local/bin" ]; then
        mkdir -p "$d"
        ln -sf "$SRC" "$d/kbuba"
        echo "installed: $d/kbuba"
        case ":$PATH:" in
            *":$d:"*) ;;
            *) echo "NOTE: $d is not on your PATH - add it to your shell profile" ;;
        esac
        # the tracker is GLOBAL (one server, every project) - decide
        # launch-at-login once, here at install time
        if [ -t 0 ]; then
            printf "Launch the tracker at login? [Y/n] "
            read -r ans
            case "$ans" in
                n|N|no|NO) echo "ok - run it when needed: python3 $(cd "$(dirname "$0")" && pwd)/tracker/serve.py (keep the terminal open)" ;;
                *) "$d/kbuba" autostart ;;
            esac
        else
            echo "tracker autostart: NOT configured (non-interactive install)."
            echo "ASK THE USER: launch the tracker at login? Yes -> run: kbuba autostart"
            echo "No -> they run 'python3 <clone>/tracker/serve.py' in a kept-open terminal."
        fi
        exit 0
    fi
done
echo "no writable bin dir found" >&2
exit 1
