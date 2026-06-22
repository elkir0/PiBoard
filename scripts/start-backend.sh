#!/bin/bash
# Backend launcher with self-restart and port cleanup
# Systemd uses Restart=no — this script handles restarts internally
cd /home/pi/piboard/backend

while true; do
    # Kill any existing Python on port 8000
    fuser -k 8000/tcp 2>/dev/null
    fuser -k 8888/tcp 2>/dev/null
    sleep 2

    echo "[BACKEND] Starting..."
    /home/pi/piboard/.venv/bin/python3 -u main.py 2>&1
    EXIT=$?

    echo "[BACKEND] Exited (code $EXIT). Cleaning up..."
    # Make sure the port is REALLY free
    fuser -k -9 8000/tcp 2>/dev/null
    fuser -k -9 8888/tcp 2>/dev/null

    # Wait for port to fully release (TIME_WAIT)
    echo "[BACKEND] Waiting for port..."
    for i in $(seq 1 30); do
        if ! fuser 8000/tcp >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    echo "[BACKEND] Restarting in 3s..."
    sleep 3
done
