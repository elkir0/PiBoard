import logging
import os
from dotenv import load_dotenv

load_dotenv()


def _num(name, default, cast):
    """Lit une var d'env numerique sans jamais crasher au boot.

    os.getenv ne renvoie le defaut que si la var est UNSET ; si elle est SET
    mais VIDE (ex: `BACKEND_PORT=` dans .env), getenv renvoie '' et
    int('')/float('') leve ValueError, tuant le backend avant uvicorn.
    Ici : vide ou invalide -> defaut degrade logue (zero-crash).
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return cast(raw)
    except (ValueError, TypeError):
        logging.warning("[CONFIG] %s invalide (%r), defaut %r", name, raw, default)
        return default


# Serveur
BACKEND_PORT = _num("BACKEND_PORT", 8000, int)
FRONTEND_PORT = _num("FRONTEND_PORT", 3000, int)

# Audio
# Micro : device ALSA explicite (ex "hw:3,0"). VIDE = autodetection d'un micro USB.
RESPEAKER_DEVICE = os.getenv("RESPEAKER_DEVICE", "")
PIPEWIRE_AIRPLAY_SINK = os.getenv("PIPEWIRE_AIRPLAY_SINK", "Devialet")
# Commande pour relancer l'UI flutter-pi apres la lecture YouTube DRM (chemin
# legacy, rarement utilise en V3). VIDE = ne rien faire (pas de chemin code en dur).
FLUTTER_RESTART_CMD = os.getenv("FLUTTER_RESTART_CMD", "")

# APIs
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # legacy (retire) — remplace par Mistral
# Mistral : Voxtral STT (voxtral-mini-latest), LLM (ministral-8b / mistral-small),
# Voxtral TTS (voxtral-mini-tts via REST /v1/audio/speech).
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# STT streaming — interrupteur entre les moteurs :
#   "vosk"     = local (Kaldi, modele FR, partiels live, 0 reseau, +150MB RAM) — defaut
#   "nemotron" = Nemotron ASR LAN (Mac mini, bien plus precis) ; Vosk reste utilise
#                pour les partiels live + l'endpointing + le REPLI si Nemotron tombe
#   "voxtral"  = cloud temps reel (Voxtral Realtime + VAD Silero, partiels live)
#   "batch"    = Voxtral non-streaming (capture fixe puis 1 transcription) — fallback
STT_MODE = os.getenv("STT_MODE", "vosk")
VOSK_MODEL_PATH = os.getenv(
    "VOSK_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "..", "models", "vosk-model-small-fr-0.22"),
)
# Nemotron ASR LAN (serveur nvidia/nemotron-3.5-asr-streaming sur :8766, ex. un Mac
# du LAN). Endpoint file-based POST /v1/transcribe (multipart). Vosk = repli auto.
# Defaut NEUTRE vide = pas de Nemotron (STT_MODE=vosk par defaut). Renseigner
# (ex http://IP_DU_SERVEUR:8766) dans le .env pour activer.
NEMOTRON_ASR_URL = os.getenv("NEMOTRON_ASR_URL", "")
# Timeout court : a chaud l'inference est ~0.6-1.5s ; si Nemotron est froid (~13s
# la 1ere fois) ou injoignable, on coupe vite et on retombe sur le final Vosk
# DEJA calcule (instantane). Pre-chauffage au boot via warmup_nemotron().
NEMOTRON_ASR_TIMEOUT = float(os.getenv("NEMOTRON_ASR_TIMEOUT", "8"))

# Passerelle LLM/TTS LOCALE (Mac mini lan-voice-gateway) — alternative GRATUITE
# a Mistral cloud. Le Pi envoie du texte, recoit intention JSON et/ou WAV.
GATEWAY_URL = os.getenv("GATEWAY_URL", "")            # ex: http://192.168.1.45:8765
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")
# Provider du cerveau : "gateway" (Ollama/Gemma local, gratuit) | "mistral" (cloud payant)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gateway")
# Provider TTS par defaut : "gateway" (Voxtral MLX local) | "voxtral" (cloud) | "piper"
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "gateway")

# Spotify
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
SPOTIFY_DEVICE_NAME = os.getenv("SPOTIFY_DEVICE_NAME", "Devialet")

# Musique — provider actif. Defaut LEGAL = radio (aucun compte requis).
#   "radio"           = radio internet (radio-browser, gratuit, sans compte) — DEFAUT
#   "local"           = bibliotheque de fichiers locale (MUSIC_LIBRARY_DIR)
#   "spotify"         = compte Spotify (API Web)
#   "spotify_connect" = recepteur Spotify Connect via go-librespot (le Pi = point de
#                       lecture ; pilote depuis l'app Spotify ; Premium requis)
#   "deezer"          = OPT-IN (zone grise ARL ; fournis ton propre DEEZER_ARL)
MUSIC_PROVIDER = os.getenv("MUSIC_PROVIDER", "radio")
# Dossier de la bibliotheque locale (si MUSIC_PROVIDER=local). Defaut ~/Music.
MUSIC_LIBRARY_DIR = os.getenv("MUSIC_LIBRARY_DIR", os.path.expanduser("~/Music"))
# API HTTP locale de go-librespot (si MUSIC_PROVIDER=spotify_connect).
GO_LIBRESPOT_API_URL = os.getenv("GO_LIBRESPOT_API_URL", "http://127.0.0.1:3678")

# Deezer (ARL-only, source musicale V3)
DEEZER_ARL = os.getenv("DEEZER_ARL", "")
DEEZER_QUALITY = os.getenv("DEEZER_QUALITY", "FLAC")  # FLAC | MP3_320 | MP3_128

# Meteo (Open-Meteo = gratuit, pas de cle). Defaut NEUTRE (Paris) = simple
# placeholder a remplacer par l'utilisateur (cf .env.example) ; aucune localisation
# personnelle codee en dur.
WEATHER_CITY = os.getenv("WEATHER_CITY", "Paris")
WEATHER_LAT = _num("WEATHER_LAT", 48.85, float)
WEATHER_LON = _num("WEATHER_LON", 2.35, float)

# UniFi Protect (cameras) — desactive proprement si non configure (host/creds vides).
UNIFI_HOST = os.getenv("UNIFI_HOST", "")
UNIFI_USER = os.getenv("UNIFI_USER", "")
UNIFI_PASS = os.getenv("UNIFI_PASS", "")
# MAC du controleur UniFi (NVR) — sert a le retrouver meme si son IP change (DHCP).
# Vide = pas d'autodecouverte par MAC (on s'appuie sur UNIFI_HOST).
UNIFI_MAC = os.getenv("UNIFI_MAC", "")

# Devialet IP Control — vide = pas de Devialet (la sortie suit le sink PipeWire par
# defaut ; le volume n'est plus pilote par l'API Devialet). Renseigner pour activer.
DEVIALET_IP = os.getenv("DEVIALET_IP", "")

# Domotique — provider derriere l'interface HomeProvider :
#   "lite"          = drivers integres Shelly/Kasa (registre config.json home.devices) — DEFAUT
#   "homeassistant" = s'appuie sur une instance Home Assistant (HA_URL + HA_TOKEN)
HOME_PROVIDER = os.getenv("HOME_PROVIDER", "lite")
HA_URL = os.getenv("HA_URL", "")        # ex http://homeassistant.local:8123
HA_TOKEN = os.getenv("HA_TOKEN", "")    # jeton d'acces longue duree (Profil HA)

# Chemins
FRONTEND_BUILD_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
