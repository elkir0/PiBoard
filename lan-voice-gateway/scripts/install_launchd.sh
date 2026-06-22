#!/bin/bash
# Installe le gateway en service launchd (démarrage auto + restart) sur le Mac mini.
# À lancer SUR le Mac mini, depuis le dossier lan-voice-gateway.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${VOXTRAL_VENV:-$HOME/.hermes/workspace/voxtral-tts/.venv}"
PLIST="$HOME/Library/LaunchAgents/com.piboard.lan-voice-gateway.plist"
LABEL="com.piboard.lan-voice-gateway"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV}/bin/python</string>
    <string>-m</string><string>uvicorn</string>
    <string>app:app</string>
    <string>--host</string><string>0.0.0.0</string>
    <string>--port</string><string>8765</string>
  </array>
  <key>WorkingDirectory</key><string>${HERE}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${HERE}/var/gateway.log</string>
  <key>StandardErrorPath</key><string>${HERE}/var/gateway.log</string>
</dict>
</plist>
PLISTEOF

mkdir -p "${HERE}/var"
UID_NUM="$(id -u)"
# macOS moderne : bootstrap dans le domaine GUI (les LaunchAgents ne démarrent
# pas via `launchctl load` depuis une session SSH non-GUI).
launchctl bootout "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/${UID_NUM}" "$PLIST"
launchctl enable "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true
launchctl kickstart -k "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true
echo "Service ${LABEL} bootstrap (gui/${UID_NUM}). Log: ${HERE}/var/gateway.log"
echo "Stop:  launchctl bootout gui/${UID_NUM}/${LABEL}"
