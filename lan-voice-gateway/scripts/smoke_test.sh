#!/bin/bash
# Smoke test du gateway. Usage: ./smoke_test.sh [HOST] [TOKEN]
#   HOST  défaut 127.0.0.1:8765 (sur le Mac) ; depuis le Pi: 192.168.1.45:8765
set -u
HOST="${1:-127.0.0.1:8765}"
TOKEN="${2:-${LAN_VOICE_TOKEN:-}}"
H=(-H "Content-Type: application/json" -H "X-LAN-VOICE-TOKEN: ${TOKEN}")

echo "== 1. /health =="
curl -sS -m 5 "http://${HOST}/health"; echo

echo "== 2. /llm/intent (musique) =="
curl -sS -m 15 "${H[@]}" -X POST "http://${HOST}/llm/intent" \
  -d '{"text":"mets la musique de Phil Collins"}'; echo

echo "== 3. /llm/chat =="
curl -sS -m 15 "${H[@]}" -X POST "http://${HOST}/llm/chat" \
  -d '{"text":"dis bonjour en une phrase"}'; echo

echo "== 4. /tts -> /tmp/reponse.wav =="
curl -sS -m 30 "${H[@]}" -X POST "http://${HOST}/tts" \
  -d '{"text":"Je lance Phil Collins.","voice":"fr_female"}' --output /tmp/reponse.wav
file /tmp/reponse.wav

echo "== 5. /voice-command =="
curl -sS -m 15 "${H[@]}" -X POST "http://${HOST}/voice-command" \
  -d '{"text":"mets la musique de Phil Collins","return_audio":false}'; echo
