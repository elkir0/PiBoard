#!/bin/bash
set -e

# Deploy PI-Board to Raspberry Pi
# Usage: ./scripts/deploy-pi.sh [pi-hostname-or-ip]

PI_HOST="${1:-raspberrypi.local}"
PI_USER="pi"
PI_DIR="/home/pi/piboard"

echo "=== PI-Board — Deploiement sur $PI_HOST ==="

# Sync files
echo "[1/5] Sync des fichiers..."
rsync -avz --exclude='.venv' --exclude='node_modules' --exclude='.git' \
  --exclude='__pycache__' --exclude='.spotify_cache' \
  ./ "${PI_USER}@${PI_HOST}:${PI_DIR}/"

# Install on Pi
echo "[2/5] Installation des dependances..."
ssh "${PI_USER}@${PI_HOST}" "cd ${PI_DIR} && bash scripts/setup.sh"

# Copy .env if exists
if [ -f .env ]; then
  echo "[3/5] Copie du .env..."
  scp .env "${PI_USER}@${PI_HOST}:${PI_DIR}/.env"
else
  echo "[3/5] Pas de .env local — pense a le creer sur le Pi"
fi

# Install systemd services
echo "[4/5] Installation des services systemd..."
ssh "${PI_USER}@${PI_HOST}" << 'REMOTE'
  sudo cp ~/piboard/systemd/piboard-backend.service /etc/systemd/system/
  sudo cp ~/piboard/systemd/piboard-kiosk.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable piboard-backend piboard-kiosk
REMOTE

# Start
echo "[5/5] Demarrage..."
ssh "${PI_USER}@${PI_HOST}" "sudo systemctl restart piboard-backend piboard-kiosk"

echo ""
echo "=== PI-Board deploye sur $PI_HOST ==="
echo "Backend: http://${PI_HOST}:8000"
echo "Logs:    ssh ${PI_USER}@${PI_HOST} 'journalctl -u piboard-backend -f'"
