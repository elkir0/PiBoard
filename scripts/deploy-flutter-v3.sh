#!/bin/bash
# Build the V3 Flutter "Salon" UI for flutter-pi and deploy it to the Pi (.152).
# Prereqs (Mac): Flutter SDK 3.41.x on PATH, flutterpi_tool activated
#   (flutter pub global activate flutterpi_tool).
# Runtime (Pi): flutter-pi libs (libdrm2 libgbm1 libegl1 libgles2 libinput10
#   libxkbcommon0 libsystemd0 + gstreamer1.0 base/good + libgstreamer-plugins-base1.0-0),
#   console-only (multi-user.target), screen on HDMI at 1920x1200.
set -e
PI_HOST="${1:-192.168.1.152}"
PI_USER="${2:-piboard}"
PI_DIR="/home/${PI_USER}/piboard-v3"
HERE="$(cd "$(dirname "$0")/../frontend-flutter" && pwd)"

export PATH="$HOME/development/flutter/bin:$PATH:$HOME/.pub-cache/bin"

echo "[1/4] flutter pub get"
cd "$HERE" && flutter pub get >/dev/null

echo "[2/4] flutterpi_tool build (release/AOT, pi4 arm64)"
flutterpi_tool build --arch=arm64 --cpu=pi4 --release

echo "[3/4] rsync bundle -> ${PI_USER}@${PI_HOST}:${PI_DIR}"
ssh "${PI_USER}@${PI_HOST}" "mkdir -p ${PI_DIR}"
rsync -az --delete "$HERE/build/flutter-pi/pi4-64/" "${PI_USER}@${PI_HOST}:${PI_DIR}/"
ssh "${PI_USER}@${PI_HOST}" "chmod +x ${PI_DIR}/flutter-pi"

echo "[4/4] restart piboard-v3.service"
ssh "${PI_USER}@${PI_HOST}" "sudo systemctl restart piboard-v3.service && sleep 6 && systemctl is-active piboard-v3.service"

echo "Done — V3 Salon UI deployed to ${PI_HOST}. Log: /tmp/piboard-v3.log"
