#!/bin/bash
echo "=== Test Audio PI-Board ==="

echo ""
echo "--- Devices ALSA ---"
arecord -l 2>/dev/null || echo "(arecord non disponible)"

echo ""
echo "--- Sinks PipeWire ---"
pactl list sinks short 2>/dev/null || echo "(pactl non disponible)"

echo ""
echo "--- Recherche Devialet ---"
pactl list sinks | grep -i devialet && echo "[OK] Devialet detecte" || echo "[!] Devialet non trouve"

echo ""
echo "--- Recherche ReSpeaker ---"
arecord -l 2>/dev/null | grep -i respeaker && echo "[OK] ReSpeaker detecte" || echo "[!] ReSpeaker non trouve"
