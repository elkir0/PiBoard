# LAN Voice Gateway (Mac mini)

Cerveau vocal **local et gratuit** pour PI-Board. Encapsule Ollama/Gemma (intentions + chat)
et le TTS Voxtral MLX local derrière une petite API LAN authentifiée. Le Raspberry Pi
reste client léger : il envoie du texte, reçoit de l'intention JSON et/ou un WAV 24 kHz.

```
Pi 4 (.152)  --HTTP+token-->  Mac mini :8765 (ce gateway)
                                 ├─ Ollama 127.0.0.1:11434  (gemma4-12b-qat-q4-k-xl, think:false)
                                 └─ Voxtral 4B TTS MLX (modèle WARM en mémoire)
```

Aucune API payante. Ollama reste sur `127.0.0.1` ; seul le gateway est exposé au LAN.

## Installation (sur le Mac mini)

```bash
cd ~/.hermes/workspace/lan-voice-gateway
VENV=~/.hermes/workspace/voxtral-tts/.venv     # on réutilise le venv TTS (mlx_audio)
$VENV/bin/pip install -r requirements.txt
cp .env.example .env && $EDITOR .env           # mettre un LAN_VOICE_TOKEN long et aléatoire
bash scripts/install_launchd.sh                # service launchd (auto-start + restart)
```

Le 1er démarrage charge le modèle TTS (~2 s) puis préchauffe Ollama et le cache TTS
des phrases fréquentes. Log : `var/gateway.log`.

## Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | état (ollama/model/tts) — sans token |
| POST | `/llm/intent` | texte → `{intent, confidence, entities, speak}` (JSON strict, fast-path regex) |
| POST | `/llm/chat` | texte → `{text}` (réponse courte) |
| POST | `/tts` | `{text, voice}` → `audio/wav` 24 kHz (cache par hash) |
| POST | `/voice-command` | texte → `{intent, speak}` (l'action s'exécute côté Pi) |

Auth : header `X-LAN-VOICE-TOKEN`. Option `ALLOWED_IPS` pour limiter au Pi.

## Test

```bash
bash scripts/smoke_test.sh 127.0.0.1:8765 "$LAN_VOICE_TOKEN"   # sur le Mac
bash scripts/smoke_test.sh 192.168.1.45:8765 "<token>"          # depuis le Pi
```

## Notes perfs
- `think:false`, `temperature:0`, `num_predict` bas, `keep_alive=30m` → intents ~3 s à chaud.
- Les commandes triviales (musique/pause/volets) sont routées **instantanément côté Pi**
  (routeur mots-clés) sans toucher Ollama. Le gateway n'est appelé que pour le fallback.
- TTS Voxtral ~1.8 s/phrase à chaud ; phrases fréquentes en cache = instantané.
- Fallback plus rapide possible (Kokoro) si besoin — non installé par défaut.
