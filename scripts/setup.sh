#!/bin/bash
set -e

echo "=== PI-Board — Installation ==="

# Mise a jour systeme
sudo apt update && sudo apt upgrade -y

# Paquets systeme
sudo apt install -y \
  python3 python3-pip python3-venv \
  chromium-browser \
  vlc \
  portaudio19-dev \
  pipewire pipewire-pulse wireplumber \
  curl git

# Node.js via NodeSource (LTS)
if ! command -v node &> /dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt install -y nodejs
fi

echo "[OK] Node $(node -v) / npm $(npm -v)"

# Python venv + deps
cd "$(dirname "$0")/.."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "[OK] Python deps installees"

# openWakeWord : telecharge les modeles de base (melspectrogram + embedding).
# Sans eux, le detecteur de wake word crashe au demarrage (NoSuchFile melspectrogram.onnx).
# Idempotent : ne re-telecharge pas si deja present.
python3 -c "import openwakeword.utils as u; u.download_models()" \
  && echo "[OK] Modeles openWakeWord de base telecharges" \
  || echo "[WARN] Echec telechargement modeles openWakeWord (wake word indisponible)"

# Frontend deps + build
cd frontend
npm install
npm run build
echo "[OK] Frontend build"

echo ""
echo "=== Installation terminee ==="
echo "Lancer avec: ./scripts/start.sh"
