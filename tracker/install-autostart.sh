#!/usr/bin/env bash
# Install the tracker as a macOS LaunchAgent: starts at login, restarts on
# crash, exits cleanly (no respawn loop) if the port is already taken.
# Re-run after moving the repo. Uninstall:
#   launchctl bootout gui/$(id -u)/com.projectkbuba.tracker
#   rm ~/Library/LaunchAgents/com.projectkbuba.tracker.plist
set -euo pipefail

LABEL=com.projectkbuba.tracker
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$(command -v python3)"
SERVE="$(cd "$(dirname "$0")" && pwd)/serve.py"
LOG="$HOME/Library/Logs/kbuba-tracker.log"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$SERVE</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed $LABEL -> http://127.0.0.1:8611 (log: $LOG)"
