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
        exit 0
    fi
done
echo "no writable bin dir found" >&2
exit 1
