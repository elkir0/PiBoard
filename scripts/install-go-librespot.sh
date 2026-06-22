#!/bin/bash
# Installe go-librespot (récepteur Spotify Connect) sur le Pi, configuré pour
# PI-Board : sortie via pipewire-pulse -> enceintes, API HTTP locale lue par le
# backend, découverte zeroconf via avahi. À lancer SUR LE PI.
#
# Ensuite : MUSIC_PROVIDER=spotify_connect dans le .env (ou via l'admin/wizard) +
# redémarrer le backend, puis sélectionner « PiBoard » dans l'app Spotify (Premium).
set -e

VERSION="${GLR_VERSION:-v0.7.4}"
DEVICE_NAME="${GLR_DEVICE_NAME:-PiBoard}"
API_PORT="${GLR_API_PORT:-3678}"
DIR="$HOME/go-librespot"
CFG_DIR="$HOME/.config/go-librespot"
UNIT="$HOME/.config/systemd/user/go-librespot.service"

arch="$(uname -m)"
case "$arch" in
  aarch64|arm64) ASSET="go-librespot_linux_arm64.tar.gz" ;;
  armv7l|armhf)  ASSET="go-librespot_linux_armv6.tar.gz" ;;
  x86_64)        ASSET="go-librespot_linux_amd64.tar.gz" ;;
  *) echo "Architecture non gérée: $arch" >&2; exit 1 ;;
esac

echo "[1/4] Téléchargement go-librespot $VERSION ($ASSET)"
mkdir -p "$DIR" && cd "$DIR"
if [ ! -x ./go-librespot ]; then
  curl -fsSL "https://github.com/devgianlu/go-librespot/releases/download/$VERSION/$ASSET" -o glr.tgz
  tar xzf glr.tgz && rm -f glr.tgz
fi
chmod +x ./go-librespot

echo "[2/4] Configuration ($CFG_DIR/config.yml)"
mkdir -p "$CFG_DIR"
cat > "$CFG_DIR/config.yml" <<CFG
device_name: $DEVICE_NAME
device_type: speaker
# Sortie via pipewire-pulse -> sink PipeWire par défaut (AirPlay/Devialet/HDMI…)
audio_backend: pulseaudio
# Spotify Connect (mDNS) via avahi
zeroconf_enabled: true
zeroconf_backend: avahi
credentials:
  type: zeroconf
  zeroconf:
    persist_credentials: false
# API HTTP locale (lue par PI-Board : now-playing + transport)
server:
  enabled: true
  address: 127.0.0.1
  port: $API_PORT
CFG

echo "[3/4] Service systemd --user"
mkdir -p "$(dirname "$UNIT")"
cat > "$UNIT" <<SVC
[Unit]
Description=go-librespot Spotify Connect receiver ($DEVICE_NAME)
After=pipewire.service pipewire-pulse.service

[Service]
ExecStart=$DIR/go-librespot
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
SVC
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
systemctl --user daemon-reload
systemctl --user enable --now go-librespot.service

echo "[4/4] Vérification"
sleep 4
systemctl --user is-active go-librespot.service && \
  echo "OK — go-librespot actif. API: http://127.0.0.1:$API_PORT"
echo
echo "Étapes suivantes :"
echo "  1) MUSIC_PROVIDER=spotify_connect dans le .env (ou admin/wizard) + redémarrer le backend"
echo "     (GO_LIBRESPOT_API_URL=http://127.0.0.1:$API_PORT si port différent)"
echo "  2) App Spotify (Premium) -> appareils -> « $DEVICE_NAME » -> lance une piste"
