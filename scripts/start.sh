#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# Activer venv
source .venv/bin/activate

# Build frontend si pas deja fait
if [ ! -d "frontend/dist" ]; then
  echo "[START] Build frontend..."
  cd frontend && npm run build && cd ..
fi

# Lancer backend en arriere-plan
echo "[START] Backend sur port 8000..."
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Attendre que le backend soit pret
sleep 2

# Lancer Chromium en mode kiosk
echo "[START] Chromium kiosk..."
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-translate \
  --no-first-run \
  --start-fullscreen \
  --autoplay-policy=no-user-gesture-required \
  --ozone-platform=wayland \
  --password-store=basic \
  --disk-cache-size=0 \
  http://localhost:8000 &

echo "[OK] PI-Board demarre (backend PID: $BACKEND_PID)"
echo "Ctrl+C pour arreter"

# Attendre le backend
wait $BACKEND_PID
