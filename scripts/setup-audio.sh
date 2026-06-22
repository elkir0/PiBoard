#!/bin/bash
# Wait for Devialet RAOP sink to appear — use whichever Phantom sink works
for i in $(seq 1 30); do
    # Any Phantom sink (IPv4 or IPv6)
    SINK=$(pactl list sinks short 2>/dev/null | grep -i phantom | head -1 | awk '{print $2}')
    if [ -n "$SINK" ]; then
        pactl set-default-sink "$SINK"
        pactl set-sink-volume "$SINK" 50%
        echo "[AUDIO] Devialet set as default (PipeWire 50%%): $SINK"
        exit 0
    fi
    sleep 2
done
echo "[AUDIO] Devialet not found after 60s"
