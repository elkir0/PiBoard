#!/bin/bash
# Capture l'ecran flutter-pi du Pi et le ramene en local (pour inspection visuelle).
# Usage : pb-shot.sh [nom_local]   -> /tmp/<nom>.png  (defaut: pb_shot)
PI="${PI:-piboard@192.168.1.152}"
NAME="${1:-pb_shot}"
ssh -o BatchMode=yes -o ConnectTimeout=12 "$PI" \
  'sudo ffmpeg -y -f kmsgrab -device /dev/dri/card1 -i - -vf hwdownload,format=bgr0 -frames:v 1 /tmp/pb_kms.png >/dev/null 2>&1 && echo OK' \
  | grep -q OK || { echo "capture KO"; exit 1; }
scp -o ConnectTimeout=12 "$PI:/tmp/pb_kms.png" "/tmp/${NAME}.png" >/dev/null 2>&1 && echo "/tmp/${NAME}.png"
