import asyncio
import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, RedirectResponse, Response
from pathlib import Path

from config import (BACKEND_PORT, FRONTEND_BUILD_DIR, MUSIC_PROVIDER, DEEZER_QUALITY,
                    LLM_PROVIDER, TTS_PROVIDER)
from admin.routes import admin_router
from audio.capture import AudioCapture
from audio.wakeword import WakeWordDetector
from audio.output import (
    ensure_selected_output, resolve_output_sink, is_devialet_sink,
    get_named_sink_volume, set_named_sink_volume, find_bluez_sink,
    is_bluetooth_sink,
)
import re as _re
import services.bluetooth as bluetooth
from admin.config_manager import config
from runtime_config import ALLOWED_CONFIG_KEYS, CONFIG_COERCE as _CONFIG_COERCE
from services.stt import STTEngine, preload_vosk, warmup_nemotron
# Providers musicaux (interface commune services.music.base.MusicProvider).
# DeezerProvider vit dans le package services.music ; le provider Spotify
# historique reste la classe MusicController, importee ici sous l'alias
# SpotifyProvider pour la fabrique ci-dessous.
from services.music import MusicProvider
from services.music.deezer_provider import DeezerProvider
from services.music.radio_provider import RadioProvider
from services.spotify import MusicController as SpotifyProvider
from services.weather import WeatherService
from services.youtube import YouTubeController
from services.cameras import CameraService
from services.devialet import DevialetService
from services.home import make_home_provider
from services.llm import LLMHandler
from services.tts import TTSEngine
from intent.router import route, extract_volume_value, extract_timer_minutes
from memory.context import memory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# Cap le thread pool par defaut (garde-fou CPU Pi 4). L'application est faite
# DANS la boucle servie par uvicorn, au demarrage du lifespan (sinon
# get_event_loop() a l'import cree une boucle jetee qui n'est jamais servie).
from concurrent.futures import ThreadPoolExecutor
logger = logging.getLogger(__name__)

# --- Shared state ---
connected_clients: list[WebSocket] = []
assistant_state = "IDLE"

# Refs fortes pour les taches fire-and-forget reellement detachees (asyncio ne
# garde qu'une weak-ref -> une tache sans ref peut etre GC avant son reveil).
_bg_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    """create_task + ref forte (anti-GC). La tache se retire a sa fin."""
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)
    return t


def _as_int(v, default: int) -> int:
    """int() tolerant : une valeur non numerique (None, 'abc', autre type) retombe
    sur le defaut au lieu de lever (les frames WS sont du JSON non fiable)."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default

# Sécurité /ws : le canal n'est pas authentifié (UI salon locale). Ces commandes
# ne sont acceptées que depuis 127.0.0.1 ; un appareil distant passe par l'admin web.
_SENSITIVE_WS = {
    "system_reboot", "system_restart_backend", "system_shutdown",
    "config_set", "screen_brightness",
    # Appairage/connexion/oubli BlueZ = mutation d'etat persistant + hijack possible
    # de la sortie audio -> reserve a 127.0.0.1 (l'UI flutter-pi est locale), comme
    # le reste. Un appareil distant passerait par l'admin web authentifie.
    "bt_pair", "bt_connect", "bt_disconnect", "bt_forget",
    # Commandes qui mutent un etat PHYSIQUE ou declenchent le pipeline vocal :
    # un client LAN distant ne doit pas pouvoir ouvrir le portail/les volets,
    # allumer la guinguette ni faire prononcer/agir l'assistant. L'UI salon
    # (127.0.0.1) garde le controle total ; le distant passe par l'admin web.
    "simulate_command", "simulate_wake",
    "domotique_portail", "domotique_roller", "domotique_roller_all", "domotique_plug",
    "audio_set_sink", "devialet_power_off", "devialet_restart",
}
# --- Core components ---
audio_capture = AudioCapture(device_name="AI-Voice")
# Fabrique provider : config.MUSIC_PROVIDER choisit la source musicale active.
# Le reste de main.py parle a `music` via l'interface commune MusicProvider.
# Defaut LEGAL = radio (aucun compte) ; local = bibliotheque ; spotify = compte ;
# deezer = OPT-IN (zone grise ARL, l'utilisateur fournit le sien). Inconnu -> radio.
def _make_music_provider(kind: str) -> MusicProvider:
    if kind == "deezer":
        logger.info("[MUSIC] Provider actif: Deezer (opt-in, ARL utilisateur)")
        return DeezerProvider()
    if kind == "spotify":
        logger.info("[MUSIC] Provider actif: Spotify")
        return SpotifyProvider()
    if kind == "spotify_connect":
        from services.music.spotify_connect_provider import SpotifyConnectProvider
        logger.info("[MUSIC] Provider actif: Spotify Connect (go-librespot)")
        return SpotifyConnectProvider()
    if kind == "local":
        from services.music.local_provider import LocalProvider
        logger.info("[MUSIC] Provider actif: Bibliotheque locale")
        return LocalProvider()
    if kind != "radio":
        logger.warning("[MUSIC] Provider '%s' inconnu -> repli radio", kind)
    logger.info("[MUSIC] Provider actif: Radio internet")
    return RadioProvider()


music: MusicProvider = _make_music_provider(MUSIC_PROVIDER)
weather = WeatherService()
youtube = YouTubeController()
cameras = CameraService()
devialet = DevialetService()
domotique = make_home_provider()
llm = LLMHandler()
tts = TTSEngine()

# État de la passerelle IA (Mac mini) pour la pastille UI : dit si on tourne en
# LOCAL GRATUIT, ou si on est retombé sur le CLOUD PAYANT (Mistral). Rafraîchi par
# gateway_monitor(), exposé via _system_info(). "unknown" tant que le 1er ping n'a pas eu lieu.
_gateway_status: dict = {
    "effective": "unknown",       # free | fallback | cloud | unknown
    "reachable": None,
    "configured_gateway": True,
    "llm_gateway": LLM_PROVIDER == "gateway",
    "tts_gateway": True,
    "model": "",
    "url": "",
}


async def broadcast(message: dict):
    for client in list(connected_clients):
        try:
            await client.send_json(message)
        except Exception:
            pass


async def set_state(new_state: str):
    global assistant_state
    assistant_state = new_state
    logger.info("[STATE] %s", new_state)
    await broadcast({"type": "state", "data": new_state})


# --- Intent handlers ---

async def handle_music_play(query: str):
    # Reconnecte l'enceinte BT choisie si elle s'est mise en veille, PUIS verrouille
    # la SORTIE CHOISIE (sinon le defaut a pu deriver / la musique partirait ailleurs).
    await _ensure_bt_output_ready()
    await ensure_selected_output()
    # Use LLM to normalize artist/track names from STT transcription
    cleaned = await llm.normalize_music_query(query)
    if cleaned and cleaned != query:
        logger.info("[PIPELINE] Query normalisee: '%s' -> '%s'", query, cleaned)
        query = cleaned

    # On ANNONCE le morceau AVANT de le lancer : la voix ne chevauche plus la
    # musique (avant : musique d'abord, puis voix par-dessus). Le top resultat
    # de search_tracks est celui que search_and_play prendra comme seed.
    if query and query.strip():
        preview = await music.search_tracks(query, limit=1)
        if not preview:
            await speak("Je n'ai pas trouvé cette musique.")
            return
        await speak(f"Je lance {preview[0]['title']} de {preview[0]['artist']}")
    else:
        await speak("C'est parti.")  # requete vide -> Flow Deezer

    result = await music.search_and_play(query)
    await broadcast({"type": "music", "data": result})
    memory.add("MUSIC_PLAY", query, result)
    if result.get("playing"):
        await asyncio.sleep(1)
        await devialet.ensure_volume()  # Prevent AirPlay volume reset
        queue = await music.get_queue()
        await broadcast({"type": "music_queue", "data": queue})


async def handle_music_pause(_query: str):
    await music.pause()
    await broadcast({"type": "music", "data": {"playing": False}})
    memory.add("MUSIC_PAUSE", "")


async def handle_music_resume(_query: str):
    await music.resume()
    current = await music.get_current()
    await broadcast({"type": "music", "data": current})
    memory.add("MUSIC_RESUME", "")
    if current.get("title"):
        await speak(f"Je reprends {current['title']}")


async def handle_music_next(_query: str):
    result = await music.next_track()
    await broadcast({"type": "music", "data": result})
    await devialet.ensure_volume()  # Prevent AirPlay volume reset
    memory.add("MUSIC_NEXT", "", result)
    if result.get("title"):
        await speak(f"Morceau suivant: {result['title']}")


async def handle_music_prev(_query: str):
    result = await music.previous_track()
    current = await music.get_current()
    await broadcast({"type": "music", "data": current})
    memory.add("MUSIC_PREV", "")


VOLUME_STEP = 5


async def set_output_volume(level: int) -> int:
    """SOURCE UNIQUE de réglage du volume. Route selon la sortie choisie :
    Devialet -> API Devialet ; sortie locale (HDMI) -> volume du sink PipeWire.
    Diffuse le message 'volume' canonique (lu par TOUTES les pages)."""
    level = max(0, min(100, int(level)))
    sink = await resolve_output_sink()
    if sink is None or is_devialet_sink(sink):
        ok = await devialet.set_volume(level)  # renvoie False si le POST echoue
    else:
        await set_named_sink_volume(sink, level)
        ok = True  # sink local : pas de retour d'erreur, on diffuse
    # Ne diffuse le volume canonique que si le reglage a vraiment pris (sinon l'UI
    # afficherait un niveau non applique).
    if ok:
        await broadcast({"type": "volume", "data": level})
    return level


async def adjust_output_volume(delta: int) -> int:
    """Monte/baisse le volume de la sortie active de `delta` points. On lit le
    volume REEL de la sortie (pas un cache perime) pour ne jamais repartir d'une
    base perimee -> plus de saut sur 'plus fort'/'moins fort'."""
    sink = await resolve_output_sink()
    if is_devialet_sink(sink) or sink is None:
        current = await devialet.get_volume_fresh()  # GET reel, None si echec (pas de cache)
        if current is None:
            logger.warning("[VOLUME] volume Devialet frais indisponible -> repli cache")
            current = await devialet.get_volume()
            if current is None:
                current = 50
    else:
        current = await get_named_sink_volume(sink)
    return await set_output_volume(current + delta)


async def handle_music_volume_up(_query: str):
    vol = await adjust_output_volume(VOLUME_STEP)
    memory.add("MUSIC_VOLUME_UP", str(vol))


async def handle_music_volume_down(_query: str):
    vol = await adjust_output_volume(-VOLUME_STEP)
    memory.add("MUSIC_VOLUME_DOWN", str(vol))


async def handle_music_volume_set(query: str):
    val = extract_volume_value(query)
    if val is not None:
        await set_output_volume(val)
        memory.add("MUSIC_VOLUME_SET", str(val))
        await speak(f"Volume a {val} pourcent")
    else:
        await speak("Je n'ai pas compris le volume souhaite")


async def handle_music_what(_query: str):
    current = await music.get_current()
    if current.get("title"):
        artist = current.get("artist", "")
        title = current.get("title", "")
        album = current.get("album", "")
        response = f"C'est {title} de {artist}"
        if album:
            response += f", album {album}"
        await speak(response)
    else:
        await speak("Il n'y a pas de musique en cours")


async def handle_music_playlist(query: str):
    if query:
        # Search for a specific playlist
        playlists = await music.get_playlists()
        for pl in playlists:
            if query.lower() in pl["name"].lower():
                result = await music.play_playlist(pl["uri"])
                await broadcast({"type": "music", "data": result})
                memory.add("MUSIC_PLAYLIST", pl["name"], result)
                await speak(f"Je lance la playlist {pl['name']}")
                return
        await speak(f"Je n'ai pas trouve de playlist {query}")
    else:
        await speak("Dis-moi quelle playlist tu veux")


async def handle_music_find(query: str):
    """Find a song by lyrics or description using LLM, then play it."""
    await speak("Je cherche cette chanson...")
    identified = await llm.identify_song(query)
    if identified:
        logger.info("[PIPELINE] Chanson identifiee: %s", identified)
        result = await music.search_and_play(identified)
        await broadcast({"type": "music", "data": result})
        memory.add("MUSIC_FIND", query, result)
        if result.get("playing"):
            await speak(f"C'est {result['title']} de {result['artist']}")
        else:
            await speak(f"J'ai identifie {identified} mais je ne la trouve pas")
    else:
        await speak("Desole, je n'ai pas reussi a identifier cette chanson")


async def handle_ai_mix(query: str):
    """Genere une selection avec le LLM et la joue via le provider actif."""
    await speak(f"Je prepare une selection pour toi...")
    songs = await llm.generate_playlist(query)
    if not songs:
        await speak("Desole, je n'ai pas reussi a creer la playlist")
        return

    # Le provider resout chaque requete texte, joue la 1re et construit la file.
    result = await music.play_tracks(songs)
    await broadcast({"type": "music", "data": result})

    if result.get("playing"):
        await asyncio.sleep(1)
        await devialet.ensure_volume()  # Prevent AirPlay volume reset
        queue = await music.get_queue()
        await broadcast({"type": "music_queue", "data": queue})
        memory.add("MUSIC_AI_MIX", query, result)
        count = (result.get("queue_size", 0) + 1) if result.get("playing") else len(songs)
        await speak(
            f"C'est parti! {count} morceaux, en commencant par "
            f"{result.get('title', '')} de {result.get('artist', '')}"
        )
    else:
        await speak("Je n'ai trouve aucun morceau pour cette selection")


async def handle_time(_query: str):
    from datetime import datetime
    now = datetime.now()
    h, m = now.hour, now.minute
    if m == 0:
        await speak(f"Il est {h} heures pile")
    else:
        await speak(f"Il est {h} heures {m}")


async def handle_repeat(_query: str):
    last = memory.last_tts
    if last:
        await speak(last)
    else:
        await speak("Je n'ai rien a repeter")


async def handle_cancel(_query: str):
    await speak("D'accord, j'annule")


async def handle_volets_open(_query: str):
    await domotique.open_all_rollers()
    await speak("J'ouvre les volets")


async def handle_volets_close(_query: str):
    await domotique.close_all_rollers()
    await speak("Je ferme les volets")


async def handle_portail(_query: str):
    await domotique.trigger_portail()
    await speak("Portail actionne")


async def handle_guinguette_on(_query: str):
    await domotique.plug_on("guinguette")
    await speak("Guinguette allumee")


async def handle_guinguette_off(_query: str):
    await domotique.plug_off("guinguette")
    await speak("Guinguette eteinte")


async def handle_greeting(_query: str):
    from datetime import datetime
    h = datetime.now().hour
    if h < 12:
        await speak("Bonjour! Comment je peux t'aider?")
    elif h < 18:
        await speak("Salut! Qu'est-ce que je peux faire pour toi?")
    else:
        await speak("Bonsoir! Je t'ecoute")


async def handle_thanks(_query: str):
    import random
    responses = ["De rien!", "Avec plaisir!", "A ton service!", "Pas de souci!"]
    await speak(random.choice(responses))


async def handle_mute(_query: str):
    await devialet.mute()
    memory.add("MUSIC_MUTE", "")


async def handle_unmute(_query: str):
    await devialet.unmute()
    memory.add("MUSIC_UNMUTE", "")


async def handle_timer(query: str):
    minutes = extract_timer_minutes(query)
    if minutes and minutes > 0:
        await speak(f"Minuteur de {minutes} minutes lance")

        async def _timer_alert():
            await asyncio.sleep(minutes * 60)
            await speak(f"Le minuteur de {minutes} minutes est termine!")

        _spawn(_timer_alert())  # ref forte : la tache (sleep long) ne sera pas GC
        memory.add("TIMER", str(minutes))
    else:
        await speak("Combien de minutes pour le minuteur?")


async def handle_weather(_query: str):
    await broadcast({"type": "page", "data": 1})
    data = await weather.get_current()
    await broadcast({"type": "weather", "data": data})
    spoken = weather.format_spoken(data)
    await speak(spoken)


async def handle_youtube_play(query: str):
    await broadcast({"type": "page", "data": 2})
    results = await youtube.search(query, limit=5)
    await broadcast({"type": "youtube_results", "data": results})
    if results:
        v = results[0]
        result = await youtube.resolve_for_flutter(v["url"])
        if result.get("playing") and result.get("url"):
            await broadcast({"type": "youtube_play_url", "data": {
                "url": result["url"],
                "title": v.get("title", ""),
                "channel": v.get("channel", ""),
                "thumbnail": v.get("thumbnail", ""),
                "watch_url": v.get("url", ""),
            }})
            await speak(f"Je lance {v['title']}")
        else:
            error_msg = result.get("error", "Erreur inconnue")
            logger.warning("[PIPELINE] YouTube play echoue: %s", error_msg)
            await broadcast({"type": "youtube_stopped", "data": {"error": error_msg}})
            await speak("Desole, je n'ai pas pu lancer la video")
    else:
        await speak(f"Je n'ai rien trouve pour {query} sur YouTube")


async def handle_youtube_stop(_query: str):
    await youtube.stop_flutter()
    await broadcast({"type": "youtube_stopped", "data": {}})
    await asyncio.sleep(1)
    current = await music.get_current()
    if current.get("playing"):
        await broadcast({"type": "music", "data": current})


async def handle_sleep(_query: str):
    global screen_sleeping
    await speak("Bonne nuit")
    await screen_off()
    screen_sleeping = True


async def handle_wake(_query: str):
    global screen_sleeping
    await screen_on()
    screen_sleeping = False
    await speak("Bonjour!")


BACKLIGHT = "/sys/class/backlight/10-0045/brightness"


def _brightness_raw(pct: int) -> int:
    """Convertit un % (10–100) en valeur matérielle backlight."""
    pct = max(10, min(100, int(pct)))
    bmax = config.get("screen", "brightness_max", 255)
    return max(1, int(bmax * pct / 100))


async def _write_backlight(raw: int):
    proc = await asyncio.create_subprocess_shell(f"echo {raw} | sudo tee {BACKLIGHT}")
    await proc.wait()


async def set_brightness(pct: int):
    """Règle la luminosité écran (10–100%), persiste, et diffuse."""
    pct = max(10, min(100, int(pct)))
    config.set("screen", "brightness", pct)
    await _write_backlight(_brightness_raw(pct))
    logger.info("[SCREEN] Luminosite %d%%", pct)
    await broadcast({"type": "screen_brightness", "data": pct})


async def screen_off():
    await _write_backlight(0)
    logger.info("[SCREEN] Ecran eteint")
    await broadcast({"type": "screen", "data": "off"})


async def screen_on():
    # Rallume à la luminosité CONFIGURÉE (plus de 255 codé en dur).
    await _write_backlight(_brightness_raw(config.get("screen", "brightness", 100)))
    logger.info("[SCREEN] Ecran allume")
    await broadcast({"type": "screen", "data": "on"})


# --- Couche tool-calling : pour les formulations naturelles que le routeur
#     par mots-cles ne capte pas, Mistral (ministral-8b) choisit un outil qui
#     mappe vers un handler EXISTANT (zero regression : on reutilise la logique
#     deja validee). Sinon, reponse conversationnelle classique. ---
VOICE_TOOLS = [
    {"type": "function", "function": {"name": "play_music",
        "description": "Lance la lecture de musique : un artiste, un genre ou un titre precis",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "artiste, genre ou titre"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "create_playlist",
        "description": "Genere et lance une playlist sur mesure pour une ambiance ou un theme",
        "parameters": {"type": "object", "properties": {"theme": {"type": "string"}}, "required": ["theme"]}}},
    {"type": "function", "function": {"name": "pause_music", "description": "Met la musique en pause", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "resume_music", "description": "Reprend la musique en pause", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "next_track", "description": "Passe au morceau suivant", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "previous_track", "description": "Revient au morceau precedent", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "whats_playing", "description": "Indique le morceau en cours de lecture", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "set_volume",
        "description": "Regle le volume sonore en pourcentage (0 a 100)",
        "parameters": {"type": "object", "properties": {"level": {"type": "integer"}}, "required": ["level"]}}},
    {"type": "function", "function": {"name": "get_weather", "description": "Donne la meteo actuelle", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "play_youtube",
        "description": "Lance une video YouTube (clip, video, recherche)",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "stop_youtube", "description": "Ferme la video YouTube en cours", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "open_volets", "description": "Ouvre les volets roulants", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "close_volets", "description": "Ferme les volets roulants", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "portail", "description": "Ouvre/actionne le portail", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "guinguette_on", "description": "Allume les lumieres de la guinguette", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "guinguette_off", "description": "Eteint les lumieres de la guinguette", "parameters": {"type": "object", "properties": {}}}},
]

TOOL_DISPATCH = {
    "play_music":      lambda a: handle_music_play(a.get("query", "")),
    "create_playlist": lambda a: handle_ai_mix(a.get("theme", "")),
    "pause_music":     lambda a: handle_music_pause(""),
    "resume_music":    lambda a: handle_music_resume(""),
    "next_track":      lambda a: handle_music_next(""),
    "previous_track":  lambda a: handle_music_prev(""),
    "whats_playing":   lambda a: handle_music_what(""),
    "set_volume":      lambda a: handle_music_volume_set(str(a.get("level", ""))),
    "get_weather":     lambda a: handle_weather(""),
    "play_youtube":    lambda a: handle_youtube_play(a.get("query", "")),
    "stop_youtube":    lambda a: handle_youtube_stop(""),
    "open_volets":     lambda a: handle_volets_open(""),
    "close_volets":    lambda a: handle_volets_close(""),
    "portail":         lambda a: handle_portail(""),
    "guinguette_on":   lambda a: handle_guinguette_on(""),
    "guinguette_off":  lambda a: handle_guinguette_off(""),
}


async def handle_general(text: str):
    context = memory.format_for_llm()
    result = await llm.route_with_tools(text, VOICE_TOOLS, context=context)

    # Outil choisi par le LLM -> on dispatche vers le handler existant.
    tool = result.get("tool")
    if tool and tool in TOOL_DISPATCH:
        logger.info("[PIPELINE] GENERAL -> outil %s %s", tool, result.get("args", {}))
        memory.add("TOOL", text, {"tool": tool, "args": result.get("args", {})})
        try:
            await TOOL_DISPATCH[tool](result.get("args", {}))
        except Exception as e:
            logger.error("[PIPELINE] Erreur outil %s: %s", tool, e)
            await speak("Desole, je n'ai pas pu faire ca.")
        return

    # Sinon : reponse conversationnelle classique.
    response = result.get("text") or "Desole, je n'ai pas bien compris."
    memory.add("GENERAL", text, {"response": response})
    await broadcast({"type": "llm_response", "data": response})
    await speak(response)


async def speak(text: str):
    memory.set_tts(text)
    await set_state("SPEAKING")
    await broadcast({"type": "speaking", "data": text})
    # No ducking — TTS and music share the same AirPlay output
    await tts.speak(text)
    await set_state("IDLE")


INTENT_HANDLERS = {
    "MUSIC_PLAY": handle_music_play,
    "MUSIC_PAUSE": handle_music_pause,
    "MUSIC_RESUME": handle_music_resume,
    "MUSIC_NEXT": handle_music_next,
    "MUSIC_PREV": handle_music_prev,
    "MUSIC_VOLUME_UP": handle_music_volume_up,
    "MUSIC_VOLUME_DOWN": handle_music_volume_down,
    "MUSIC_VOLUME_SET": handle_music_volume_set,
    "MUSIC_WHAT": handle_music_what,
    "MUSIC_PLAYLIST": handle_music_playlist,
    "MUSIC_FIND": handle_music_find,
    "MUSIC_AI_MIX": handle_ai_mix,
    "YOUTUBE_PLAY": handle_youtube_play,
    "YOUTUBE_STOP": handle_youtube_stop,
    "WEATHER": handle_weather,
    "SLEEP": handle_sleep,
    "WAKE": handle_wake,
    "TIME": handle_time,
    "REPEAT": handle_repeat,
    "CANCEL": handle_cancel,
    "TIMER": handle_timer,
    "DOMOTIQUE_VOLETS_OPEN": handle_volets_open,
    "DOMOTIQUE_VOLETS_CLOSE": handle_volets_close,
    "DOMOTIQUE_PORTAIL": handle_portail,
    "DOMOTIQUE_GUINGUETTE_ON": handle_guinguette_on,
    "DOMOTIQUE_GUINGUETTE_OFF": handle_guinguette_off,
    "GREETING": handle_greeting,
    "THANKS": handle_thanks,
    "MUSIC_MUTE": handle_mute,
    "MUSIC_UNMUTE": handle_unmute,
    "GENERAL": handle_general,
}


# --- Voice pipeline ---

_pending_handler = None

async def on_transcript(text: str, is_final: bool):
    global _pending_handler
    await broadcast({"type": "transcript", "data": {"text": text, "final": is_final}})

    if is_final and text.strip():
        logger.info("[PIPELINE] Transcription: %s", text)
        # Don't run handler here (recv_loop gets cancelled by send_audio)
        # Instead, store it and run after send_audio completes
        # Pass active context so "stop" routes correctly (youtube vs music)
        try:
            is_yt = youtube.is_playing
        except Exception:
            is_yt = False
        active_ctx = "youtube" if is_yt else memory.domain
        intent, query = route(text, active_context=active_ctx)
        await broadcast({"type": "intent", "data": {"intent": intent, "query": query}})
        _pending_handler = (intent, query)


async def on_wake():
    global assistant_state
    # Don't trigger if already busy
    if assistant_state != "IDLE":
        return

    logger.info("[PIPELINE] Wake word detecte!")
    # Pause wake word detection during interaction
    if wake_detector:
        wake_detector.paused = True

    # No volume ducking — causes more problems than it solves
    _wake_saved_vol = None

    await set_state("LISTENING")

    audio_queue = audio_capture.subscribe()

    # Drain ~0.5s of audio to skip the tail end of the wake word
    drain_end = asyncio.get_event_loop().time() + 0.5
    while asyncio.get_event_loop().time() < drain_end:
        try:
            audio_queue.get_nowait()
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.05)

    stt = None
    try:
        global _pending_handler
        _pending_handler = None

        stt = STTEngine(on_transcript=on_transcript)
        await stt.start()
        await stt.send_audio(audio_queue, duration_s=8.0)
    except Exception as e:
        logger.error("[PIPELINE] Erreur STT: %s", e)
    finally:
        audio_capture.unsubscribe(audio_queue)
        # Ferme proprement le STT (client cloud, stream) meme si une exception a
        # eu lieu entre start() et send_audio -> evite une fuite de session voxtral.
        _stt_stop = getattr(stt, "stop", None)
        if _stt_stop:
            try:
                await _stt_stop()
            except Exception:
                pass

    # Run the handler AFTER send_audio (not inside recv_loop)
    if _pending_handler:
        intent, query = _pending_handler
        _pending_handler = None
        await set_state("PROCESSING")
        handler = INTENT_HANDLERS.get(intent, handle_general)
        try:
            await handler(query)
        except Exception as e:
            logger.error("[PIPELINE] Erreur handler %s: %s", intent, e)

    # Volume not ducked — nothing to restore

    # Return to IDLE
    await set_state("IDLE")

    # Re-enable wake word after a delay (avoid self-trigger from TTS)
    await asyncio.sleep(6.0)
    if wake_detector:
        wake_detector.reset_cooldown()  # Reset cooldown so music doesn't re-trigger immediately
        wake_detector.paused = False
        logger.info("[PIPELINE] Wake word reactif")


    # Volume watchdog removed — user controls volume manually


async def music_state_poller():
    """Watch librespot journal logs for real-time track changes.

    Specifique a Spotify/librespot (parsing du journal raspotify). Pour Deezer,
    le now-playing est pousse par le provider (broadcast on_track_change) : on
    sort immediatement sans rien parser pour ne pas errer.
    """
    if MUSIC_PROVIDER != "spotify":
        # Deezer/radio : pas de journal librespot. Le now-playing arrive via le
        # provider (on_track_change, event mpv). Ici on pousse la progression
        # REELLE toutes les 2 s pour que la barre reste synchro cote UI.
        #
        # spotify_connect : RECEPTEUR sans mpv -> AUCUN event on_track_change. Le
        # now-playing complet (titre/artiste/pochette) n'existe QUE via ce poll
        # de l'API go-librespot. On diffuse donc le `music` complet a chaque
        # changement d'URI (et un playing:False quand la session s'arrete).
        push_full = MUSIC_PROVIDER == "spotify_connect"
        last_uri = None
        while True:
            try:
                cur = await music.get_current()
                if cur.get("playing"):
                    if push_full and cur.get("uri") != last_uri:
                        last_uri = cur.get("uri")
                        await broadcast({"type": "music", "data": cur})
                    await broadcast({"type": "music_progress", "data": {
                        "progress_ms": cur.get("progress_ms", 0),
                        "duration_ms": cur.get("duration_ms", 0),
                        "playing": True,
                    }})
                elif push_full and last_uri is not None:
                    last_uri = None
                    await broadcast({"type": "music", "data": {"playing": False}})
            except Exception as e:
                logger.debug("[POLLER] progress: %s", e)
            await asyncio.sleep(2)
        return
    import subprocess, re, time as _time
    last_uri = ""
    last_track_data = {}
    track_start_time = 0.0

    def _get_latest_track():
        """Parse librespot journal for the last loaded track."""
        try:
            result = subprocess.run(
                ["journalctl", "-u", "raspotify", "--since", "30 sec ago", "--no-pager", "-q"],
                capture_output=True, text=True, timeout=3,
            )
            # Find last "Loading <Title> with Spotify URI <spotify:track:ID>"
            pattern = r'Loading <(.+?)> with Spotify URI <(spotify:track:\w+)>'
            matches = re.findall(pattern, result.stdout)
            if matches:
                title, uri = matches[-1]
                # Find duration from "loaded" line
                dur_pattern = r'<' + re.escape(title) + r'> \((\d+) ms\) loaded'
                dur_match = re.findall(dur_pattern, result.stdout)
                duration = int(dur_match[-1]) if dur_match else 0
                return {"title": title, "uri": uri, "duration_ms": duration}
        except Exception:
            pass
        return None

    while True:
        try:
            await asyncio.sleep(5)
            if not connected_clients:
                continue
            if _time.time() < getattr(music, '_poller_skip_until', 0):
                continue

            track_info = await asyncio.get_event_loop().run_in_executor(None, _get_latest_track)
            if not track_info:
                continue

            uri = track_info["uri"]
            if uri == last_uri:
                # Same track — update progress based on elapsed time
                if last_track_data and track_start_time:
                    elapsed = int((_time.time() - track_start_time) * 1000)
                    last_track_data["progress_ms"] = min(elapsed, last_track_data.get("duration_ms", 0))
                    await broadcast({"type": "music", "data": last_track_data})
                continue

            # New track! Fetch metadata from Spotify API
            last_uri = uri
            track_start_time = _time.time()
            track_id = uri.replace("spotify:track:", "")
            try:
                loop = asyncio.get_event_loop()
                sp_track = await asyncio.wait_for(
                    loop.run_in_executor(None, music._sp.track, track_id),
                    timeout=5,
                )
                if sp_track:
                    last_track_data = {
                        "playing": True,
                        "title": sp_track["name"],
                        "artist": ", ".join(a["name"] for a in sp_track["artists"]),
                        "album": sp_track["album"]["name"],
                        "cover": sp_track["album"]["images"][0]["url"] if sp_track["album"]["images"] else None,
                        "progress_ms": 0,
                        "duration_ms": sp_track.get("duration_ms", track_info["duration_ms"]),
                    }
                    await broadcast({"type": "music", "data": last_track_data})
                    logger.info("[POLLER] Track: %s — %s", last_track_data["title"], last_track_data["artist"])
                    # Also fetch queue
                    try:
                        queue = await asyncio.wait_for(music.get_queue(), timeout=5)
                        await broadcast({"type": "music_queue", "data": queue})
                    except Exception:
                        pass
            except Exception as e:
                # Fallback: use title from logs without metadata
                last_track_data = {
                    "playing": True,
                    "title": track_info["title"],
                    "artist": "",
                    "album": "",
                    "cover": None,
                    "progress_ms": 0,
                    "duration_ms": track_info["duration_ms"],
                }
                await broadcast({"type": "music", "data": last_track_data})
                logger.debug("[POLLER] Track (no metadata): %s — %s", track_info["title"], e)
        except Exception as e:
            logger.debug("[POLLER] %s", e)
            await asyncio.sleep(10)


def _audio_busy() -> bool:
    """Le micro capte la sortie Devialet (pas d'AEC) : pendant la musique ou le
    TTS, on durcit le seuil du wake word pour eviter les faux declenchements."""
    if assistant_state == "SPEAKING":
        return True
    try:
        player = getattr(music, "_player", None)
        return bool(player and player.is_playing)
    except Exception:
        return False


async def voice_pipeline():
    global wake_detector
    wake_detector = WakeWordDetector(on_wake=on_wake)
    wake_detector.busy_check = _audio_busy
    await wake_detector.start()
    audio_queue = audio_capture.subscribe()
    asyncio.create_task(audio_capture.start())
    await wake_detector.process(audio_queue)

wake_detector = None

screen_sleeping = False
_screen_sleep_timeout = 120  # seconds of inactivity before screen dims (when not in sleep hours)

async def touch_wake_listener():
    """Listen for double-tap on touchscreen to wake screen from sleep."""
    import struct, glob, time as _time

    # Find touchscreen
    touch_dev = None
    for d in glob.glob("/dev/input/event*"):
        try:
            name_path = f"/sys/class/input/{d.split('/')[-1]}/device/name"
            with open(name_path) as f:
                name = f.read().strip().lower()
                if "touch" in name or "ft5" in name or "edt" in name:
                    touch_dev = d
                    break
        except Exception:
            continue

    if not touch_dev:
        logger.warning("[TOUCH] No touchscreen found")
        return

    logger.info("[TOUCH] Wake listener on %s", touch_dev)
    loop = asyncio.get_event_loop()

    def _watch_taps():
        """Blocking: wait for double-tap, return True."""
        last_tap = 0
        with open(touch_dev, "rb") as f:
            while True:
                data = f.read(24)
                if len(data) < 24:
                    continue
                _, _, ev_type, ev_code, ev_value = struct.unpack("llHHi", data)
                # BTN_TOUCH down
                if ev_type == 1 and ev_code == 330 and ev_value == 1:
                    now = _time.monotonic()
                    if now - last_tap < 0.4:
                        return True  # Double tap
                    last_tap = now

    while True:
        try:
            global screen_sleeping
            if not screen_sleeping:
                await asyncio.sleep(2)
                continue
            # Screen is sleeping — wait for double tap
            tapped = await loop.run_in_executor(None, _watch_taps)
            if tapped and screen_sleeping:
                logger.info("[TOUCH] Double tap — waking screen")
                await screen_on()
                screen_sleeping = False
                # Keep screen on for 2 minutes then let scheduler decide
                await asyncio.sleep(120)
        except Exception as e:
            logger.debug("[TOUCH] %s", e)
            await asyncio.sleep(5)


async def screen_scheduler():
    """Auto sleep écran 22h-6h. Chaque action une fois par transition.
    PLUS DE CHANGEMENT AUTO DE VOLUME (supprimé : le volume ne bouge que sur
    demande de l'utilisateur — fini les sauts nuit/jour)."""
    from datetime import datetime
    global screen_sleeping

    def _is_sleep(h: int) -> bool:
        # Horaires de veille lus depuis la config (réglables depuis l'UI).
        start = int(config.get("screen", "sleep_hour_start", 22))
        end = int(config.get("screen", "sleep_hour_end", 6))
        return (start <= h or h < end) if start > end else (start <= h < end)

    # Initialize state based on current time (avoid re-triggering on restart)
    was_sleep = _is_sleep(datetime.now().hour)

    if was_sleep:
        await screen_off()
        screen_sleeping = True
        logger.info("[SCREEN] Demarrage en mode dodo")

    while True:
        await asyncio.sleep(60)
        in_sleep = _is_sleep(datetime.now().hour)

        # Screen transitions
        if in_sleep and not was_sleep:
            await screen_off()
            screen_sleeping = True
            logger.info("[SCREEN] Auto dodo (22h)")
        elif not in_sleep and was_sleep:
            await screen_on()
            screen_sleeping = False
            logger.info("[SCREEN] Auto reveil (6h)")
        was_sleep = in_sleep


# --- Audio sinks ---

def _sink_label(name: str, desc: str) -> str | None:
    """Libelle convivial d'un sink, ou None s'il faut le masquer (interne)."""
    low = name.lower()
    if "raop" in low and "phantom" in low:
        return "Devialet (Phantom)"
    if "raop" in low:
        # raop_sink.<NOM>.local.<ip>.<port> -> <NOM> lisible
        parts = name.split(".")
        nm = parts[1] if len(parts) > 1 else name
        return f"{nm.replace('-', ' ')} (AirPlay)"
    if "hdmi" in low:
        return "Écran HDMI"
    if low.startswith("bluez_output"):
        return f"{desc} (Bluetooth)" if desc else "Enceinte Bluetooth"
    return None  # mailbox / auto_null / monitor interne


async def _get_audio_sinks() -> dict:
    """Liste UNIFIEE des sorties selectionnables : toutes les sorties PRESENTES
    (HDMI, AirPlay/RAOP nommees, enceintes BT connectees) + les enceintes BT
    APPAIREES mais deconnectees (selectionnables -> connectees a la volee)."""
    import subprocess
    loop = asyncio.get_event_loop()

    def _query():
        default = subprocess.run(
            ['pactl', 'get-default-sink'], capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        raw = subprocess.run(
            ['pactl', 'list', 'sinks'], capture_output=True, text=True, timeout=5,
        ).stdout
        sinks, current = [], {}
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith('Sink #'):
                if current:
                    sinks.append(current)
                current = {}
            elif line.startswith('Name:'):
                current['name'] = line.split(':', 1)[1].strip()
            elif line.startswith('Description:'):
                current['description'] = line.split(':', 1)[1].strip()
        if current:
            sinks.append(current)

        out, present_macs = [], set()
        for s in sinks:
            nm = s.get('name', '')
            lbl = _sink_label(nm, s.get('description', ''))
            if not lbl:
                continue
            is_bt = nm.lower().startswith('bluez_output')
            if is_bt:
                m = _mac_from_bluez_sink(nm)
                if m:
                    present_macs.add(m)
            out.append({'name': nm, 'description': lbl, 'is_default': nm == default,
                        'bluetooth': is_bt, 'connected': True})
        return default, out, present_macs

    try:
        default, out, present_macs = await loop.run_in_executor(None, _query)
        # Enceintes BT appairees deconnectees -> entrees selectionnables.
        try:
            for d in await bluetooth.list_devices(paired_only=True):
                if d.get('audio') and d['mac'] not in present_macs:
                    name = "bluez_output." + d['mac'].replace(':', '_').upper() + ".1"
                    out.append({'name': name, 'description': f"{d['name']} (Bluetooth)",
                                'is_default': False, 'bluetooth': True, 'connected': False,
                                'mac': d['mac']})
        except Exception:
            pass
        return {'default': default, 'sinks': out}
    except Exception as e:
        logger.error("[AUDIO] Erreur liste sinks: %s", e)
        return {'default': '', 'sinks': [], 'error': str(e)}


async def _set_audio_sink(sink_name: str, persist: bool = True) -> dict:
    """Set default PipeWire/PulseAudio sink and move all active streams to it.
    persist=True (defaut) : ecrit output_sink (choix manuel = nouvelle base).
    persist=False : override transitoire (bascule auto BT, ne touche pas la base)."""
    import subprocess
    loop = asyncio.get_event_loop()
    try:
        def _apply():
            # 1. Set default sink
            subprocess.run(
                ['pactl', 'set-default-sink', sink_name],
                check=True, timeout=5,
            )
            # 2. Move ALL active sink-inputs (playing streams) to the new sink
            inputs_raw = subprocess.run(
                ['pactl', 'list', 'sink-inputs', 'short'],
                capture_output=True, text=True, timeout=5,
            ).stdout
            moved = 0
            for line in inputs_raw.strip().splitlines():
                if not line.strip():
                    continue
                input_id = line.split()[0]
                try:
                    subprocess.run(
                        ['pactl', 'move-sink-input', input_id, sink_name],
                        check=True, timeout=5,
                    )
                    moved += 1
                except Exception:
                    pass
            return sink_name, moved

        result_name, moved = await loop.run_in_executor(None, _apply)
        # PERSISTE le choix (choix manuel) : source de vérité de la sortie, appliquée
        # à tous les émetteurs (musique/TTS/YouTube) et après reboot. La bascule auto
        # BT passe persist=False -> override transitoire sans écraser la base.
        if persist:
            config.set("audio", "output_sink", result_name)
        logger.info("[AUDIO] Sortie choisie: %s (%d flux deplaces, persist=%s)",
                    result_name, moved, persist)
        return {'success': True, 'default': result_name, 'moved': moved}
    except Exception as e:
        logger.error("[AUDIO] Erreur set sink: %s", e)
        return {'success': False, 'error': str(e)}


# --- Bluetooth (enceintes) ---

# Enceintes que l'utilisateur a explicitement deconnectees : la reconnexion auto
# les ignore tant qu'il ne les reconnecte/reappaire pas manuellement.
_bt_user_disconnected: set[str] = set()

# Appareils dont une action (pair/connect/...) est en cours : anti-doublon (taps
# repetes de l'UI) pour ne pas lancer des bluetoothctl concurrents.
_bt_inflight: set[str] = set()

# Vrai pendant qu'un changement MANUEL de sortie (audio_set_sink) est en cours :
# empeche bluetooth_monitor de rebasculer vers le Devialet sur un idle-drop bref
# de l'enceinte juste apres le set utilisateur (course poll 5s vs connect+set).
_manual_sink_switch_inflight = False

def _mac_from_bluez_sink(name: str) -> str | None:
    """MAC depuis un nom de sink bluez_output.AA_BB_..._FF.1 -> AA:BB:...:FF."""
    m = _re.search(r"bluez_output\.([0-9A-Fa-f]{2}(?:_[0-9A-Fa-f]{2}){5})", name or "")
    return m.group(1).replace("_", ":").upper() if m else None


# Adresse MAC stricte : defense en profondeur contre l'injection d'options/newline
# dans bluetoothctl (le MAC vient brut du WS, cf bt_pair/connect/disconnect/forget).
_MAC_RE = _re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


async def _ensure_bt_output_ready():
    """RECONNEXION A LA LECTURE : si la sortie choisie est une enceinte BT
    actuellement deconnectee (idle-power-save de l'enceinte), on la reconnecte
    AVANT de jouer (sinon la musique partirait sur le Devialet de repli).
    Respecte une deconnexion manuelle. Appelee au debut de chaque lecture."""
    try:
        chosen = config.get("audio", "output_sink", "") or ""
        if not is_bluetooth_sink(chosen):
            return
        mac = _mac_from_bluez_sink(chosen)
        if not mac or mac in _bt_user_disconnected:
            return
        if await find_bluez_sink(mac):
            return  # deja connectee
        logger.info("[BLUETOOTH] reconnexion a la lecture -> %s", mac)
        ok, _err = await bluetooth.connect(mac)
        if ok:
            for _ in range(8):  # attend que le sink reapparaisse
                if await find_bluez_sink(mac):
                    break
                await asyncio.sleep(1)
    except Exception as e:
        logger.error("[BLUETOOTH] reconnexion a la lecture: %s", e)


async def _bt_state() -> dict:
    """Etat Bluetooth complet pour l'UI."""
    try:
        return {
            "available": await bluetooth.is_available(),
            "scanning": bluetooth.is_scanning(),
            "devices": await bluetooth.list_devices(),
        }
    except Exception as e:
        logger.error("[BLUETOOTH] etat: %s", e)
        return {"available": False, "scanning": False, "devices": []}


async def _bt_scan_task():
    """Lance une decouverte temporisee et pousse la liste a chaque rafraichissement."""
    async def _tick():
        state = await _bt_state()
        state["scanning"] = True
        await broadcast({"type": "bt_devices", "data": state})
    await _tick()
    await bluetooth.start_scan(seconds=20, on_tick=_tick)
    await broadcast({"type": "bt_devices", "data": await _bt_state()})


async def _bt_action(op: str, mac: str):
    """Execute une action BT (pair/connect/disconnect/forget) et notifie l'UI.
    La bascule auto sur connexion est geree par bluetooth_monitor()."""
    fn = {
        "bt_pair": bluetooth.pair,
        "bt_connect": bluetooth.connect,
        "bt_disconnect": bluetooth.disconnect,
        "bt_forget": bluetooth.forget,
    }.get(op)
    if fn is None:
        return
    # Valide le MAC AVANT tout bluetoothctl (rejette options/newline injectes).
    if not _MAC_RE.match(mac or ""):
        logger.warning("[BLUETOOTH] MAC invalide refusee: %r", mac)
        return
    # Anti-doublon : ignore une 2e action pour le MEME appareil tant que la 1ere
    # tourne (les taps repetes de l'UI lancaient des bluetoothctl concurrents qui
    # se telescopaient -> appairage corrompu). Defense a la source.
    if mac in _bt_inflight:
        logger.info("[BLUETOOTH] action %s ignoree (deja en cours pour %s)", op, mac)
        return
    _bt_inflight.add(mac)
    # Intention utilisateur : une deconnexion manuelle desactive la reconnexion auto ;
    # une connexion/appairage manuel la reactive.
    if op == "bt_disconnect":
        _bt_user_disconnected.add(mac)
    elif op in ("bt_connect", "bt_pair"):
        _bt_user_disconnected.discard(mac)
    try:
        ok, err = await fn(mac)
    except Exception as e:
        ok, err = False, str(e)
    finally:
        _bt_inflight.discard(mac)
    # Deconnexion manuelle reussie : si l'enceinte etait la sortie memorisee, on
    # repasse sur le Devialet (sinon la reconnexion a la lecture la rebrancherait).
    if op == "bt_disconnect" and ok:
        chosen = config.get("audio", "output_sink", "") or ""
        if _mac_from_bluez_sink(chosen) == mac:
            config.set("audio", "output_sink", "")
    await broadcast({"type": "bt_action_result",
                     "data": {"ok": ok, "op": op, "mac": mac, "error": err}})
    # Laisse le temps au sink BT d'apparaitre/disparaitre, puis rafraichit.
    await asyncio.sleep(1.0)
    await broadcast({"type": "bt_devices", "data": await _bt_state()})


async def bluetooth_monitor():
    """Suit les enceintes BT : sur connexion (manuelle, a la lecture, ou device-
    initiated quand l'enceinte s'allume) -> bascule la sortie dessus ET la memorise
    (output_sink) ; sur deconnexion -> restaure le Devialet. PAS de reconnexion
    periodique (l'enceinte idle-drop quand rien ne joue ; on la reconnecte a la
    LECTURE, cf. _ensure_bt_output_ready). Zero-crash."""
    prev_connected: set[str] = set()
    await asyncio.sleep(8)  # laisse le reste des services demarrer
    while True:
        try:
            # Regime permanent : seulement les appareils appaires (petit ensemble) ->
            # pas de rafale d'appels `info` sur tout le cache de decouverte.
            devices = await bluetooth.list_devices(paired_only=True)
            connected = {d["mac"] for d in devices if d["connected"]}

            # Nouvelles connexions -> PAS de bascule auto (priorite Devialet).
            # L'enceinte BT ne devient la sortie QUE si l'utilisateur la choisit
            # dans "Sortie". On rafraichit juste l'UI (selecteur + section BT).
            if connected - prev_connected:
                await broadcast({"type": "audio_sinks", "data": await _get_audio_sinks()})
                await broadcast({"type": "bt_devices", "data": await _bt_state()})

            # Deconnexions -> restaure le Devialet (en DEPLACANT les flux, car mpv
            # --ao=pulse ne suit pas un changement de defaut a chaud). output_sink
            # reste l'enceinte (memorisee) -> reconnexion a la prochaine lecture.
            dropped = prev_connected - connected
            if dropped and not _manual_sink_switch_inflight:
                # output_sink memorise = l'enceinte (absente) -> resolve renvoie le
                # Devialet de repli. persist=False : on garde l'enceinte memorisee.
                # On NE restaure PAS si un changement manuel de sortie est en cours
                # (idle-drop bref pendant le connect+set utilisateur -> sinon on
                # ecraserait le choix de l'utilisateur juste apres son set).
                base = await resolve_output_sink()
                if base:
                    await _set_audio_sink(base, persist=False)
                else:
                    await ensure_selected_output()
                await broadcast({"type": "audio_sinks", "data": await _get_audio_sinks()})
                await broadcast({"type": "bt_devices", "data": await _bt_state()})
                logger.info("[BLUETOOTH] deconnexion(s) -> retour Devialet")

            prev_connected = connected
        except Exception as e:
            logger.error("[BLUETOOTH] monitor: %s", e)
        await asyncio.sleep(5)


# --- Devialet power / redemarrage ---

async def _devialet_wake():
    """Reveille le Devialet de veille : on re-verrouille la sortie (le sink RAOP
    peut mettre quelques secondes a reapparaitre) puis un court son AirPlay le
    sort de veille et confirme."""
    woke = False
    for _ in range(10):
        if await ensure_selected_output():
            woke = True
            break
        await asyncio.sleep(2)
    if not woke:
        # Aucun sink resolu apres 20s : pas de TTS perdu vers nulle part.
        logger.warning("[DEVIALET] reveil: aucune sortie resolue (enceinte injoignable?)")
        return
    try:
        await tts.speak("Enceintes prêtes.")
    except Exception as e:
        logger.warning("[DEVIALET] reveil TTS: %s", e)


async def handle_devialet_power_off():
    logger.info("[DEVIALET] Mise en veille demandee")
    await devialet.power_off()
    await asyncio.sleep(1.5)
    await broadcast({"type": "devialet_status", "data": await devialet.get_status()})


async def handle_devialet_restart():
    """Redemarre les enceintes : veille (powerOff) puis reveil par l'audio.
    L'IP Control n'a pas de reboot dur — c'est le cycle veille/reveil."""
    logger.info("[DEVIALET] Redemarrage demande (veille + reveil)")
    await broadcast({"type": "devialet_restarting", "data": True})
    await devialet.power_off()
    await asyncio.sleep(8)          # laisse le systeme passer en veille
    await _devialet_wake()
    await broadcast({"type": "devialet_restarting", "data": False})
    await broadcast({"type": "devialet_status", "data": await devialet.get_status()})


# --- App lifecycle ---

async def _start_devialet():
    try:
        await devialet.start()
    except Exception as e:
        logger.error("[DEVIALET] Erreur demarrage: %s", e)


async def _start_domotique():
    try:
        await domotique.start()
    except Exception as e:
        logger.error("[DOMOTIQUE] Erreur demarrage: %s", e)


async def _delayed_shutdown():
    """Shutdown the Pi after a short delay."""
    await asyncio.sleep(2)
    proc = await asyncio.create_subprocess_exec(
        "sudo", "shutdown", "-h", "now",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()


async def _delayed_reboot():
    """Redemarre la machine apres un court delai (piboard a sudo NOPASSWD)."""
    logger.warning("[SYSTEM] Reboot machine demande")
    await asyncio.sleep(2)
    proc = await asyncio.create_subprocess_exec(
        "sudo", "reboot",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()


def _restart_backend():
    """Redemarre le service backend via une unite transitoire decouplee du
    cgroup (sinon le process se tuerait avant d'avoir relance le service)."""
    import subprocess
    logger.warning("[SYSTEM] Restart backend demande")
    subprocess.Popen([
        "systemd-run", "--user", "--collect", "--on-active=1",
        "systemctl", "--user", "restart", "ekip-backend",
    ])


async def _system_info() -> dict:
    """Infos systeme pour l'UI (URL admin du QR, etc.)."""
    import socket
    hostname = socket.gethostname()
    ip = ""
    try:
        proc = await asyncio.create_subprocess_exec(
            "hostname", "-I",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await proc.communicate()
        parts = out.decode().split()
        ip = parts[0] if parts else ""
    except Exception:
        pass
    return {
        "hostname": hostname,
        "ip": ip,
        "admin_url": f"http://{hostname}.local:8000/admin/",
        "admin_url_ip": f"http://{ip}:8000/admin/" if ip else "",
        "gateway": _gateway_status,
    }


async def gateway_monitor():
    """Ping périodique de la passerelle IA (Mac mini) pour la pastille UI.

    Aujourd'hui le Pi ne SAIT pas qu'il est retombé sur le cloud payant : llm.py/
    tts.py ne testent que la présence de l'URL et basculent sur Mistral à la volée
    quand une requête échoue. Ce moniteur ajoute une vraie connaissance « joignable
    ou non » -> la pastille peut prévenir AVANT une commande vocale facturée.
    Mirroir léger de bluetooth_monitor ; diffuse system_info quand l'état change."""
    global _gateway_status
    while True:
        try:
            gw = llm._gw  # GatewayClient partagé (url+token depuis .env)
            reachable, model = False, ""
            if gw.available():
                try:
                    h = await gw.health(timeout=4)
                    # ollama doit être chaud, sinon le LLM échoue et retombe sur Mistral.
                    reachable = bool(h.get("ok")) and bool(h.get("ollama"))
                    model = (h.get("model") or "") if reachable else ""
                except Exception:
                    reachable = False
            llm_gw = (LLM_PROVIDER == "gateway")
            tts_gw = (config.get("tts", "provider", TTS_PROVIDER) == "gateway")
            # Le COÛT vient du LLM (Mistral cloud = payant). Le TTS, lui, retombe sur
            # Piper (FR local GRATUIT) si la passerelle tombe -> pas un signal de coût.
            # On pilote donc la pastille sur le LLM, le vrai poste payant.
            if not llm_gw:
                effective = "cloud"        # cerveau IA sur Mistral cloud = choisi, payant
            elif reachable:
                effective = "free"         # LLM local gratuit (Mac mini)
            else:
                effective = "fallback"     # voulait la passerelle mais injoignable -> Mistral payant
            new = {
                "effective": effective, "reachable": reachable,
                "configured_gateway": llm_gw,
                "llm_gateway": llm_gw, "tts_gateway": tts_gw,
                "model": model, "url": gw.url,
            }
            if new != _gateway_status:
                _gateway_status = new
                logger.info("[GATEWAY] etat=%s reachable=%s model=%s", effective, reachable, model or "-")
                await broadcast({"type": "system_info", "data": await _system_info()})
        except Exception as e:
            logger.error("[GATEWAY] monitor: %s", e)
        await asyncio.sleep(25)


async def _start_spotify():
    """Start Spotify in background so rate limits don't block server startup."""
    try:
        await music.start()
    except Exception as e:
        logger.error("[SPOTIFY] Erreur au demarrage: %s", e)


async def _start_oauth_proxy():
    """Tiny HTTP server on port 8888 that redirects to port 8000.

    Spotify OAuth redirect URI is http://127.0.0.1:8888/callback but
    FastAPI runs on port 8000. This proxy catches the callback and redirects.
    """
    async def handle_client(reader, writer):
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5)
            # Read remaining headers (discard)
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=2)
                if line == b'\r\n' or not line:
                    break
            # Extract path from "GET /callback?code=xxx HTTP/1.1"
            parts = request_line.decode().split()
            path = parts[1] if len(parts) >= 2 else "/"
            redirect_url = f"http://127.0.0.1:8000{path}"
            response = (
                f"HTTP/1.1 302 Found\r\n"
                f"Location: {redirect_url}\r\n"
                f"Connection: close\r\n\r\n"
            )
            writer.write(response.encode())
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    try:
        server = await asyncio.start_server(handle_client, "127.0.0.1", 8888)
        logger.info("[OAUTH] Proxy port 8888 -> 8000 actif")
        return server
    except OSError as e:
        logger.warning("[OAUTH] Port 8888 indisponible: %s", e)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[PI-BOARD] Demarrage des services...")
    # Cap le thread pool sur la boucle REELLEMENT servie (avant tout run_in_executor).
    try:
        asyncio.get_running_loop().set_default_executor(
            ThreadPoolExecutor(max_workers=4, thread_name_prefix="piboard"))
    except Exception as e:
        logger.warning("[PI-BOARD] executor cap: %s", e)
    # Wire broadcast so Spotify can push status changes to frontend
    music.set_broadcast(broadcast)
    # Start Spotify in background — don't block server startup on rate limits
    asyncio.create_task(_start_spotify())
    await cameras.start()
    # Start Devialet and Domotique sequentially BEFORE voice pipeline
    # (if done in parallel with wakeword, CPU spikes cause SIGKILL on Pi 4)
    await _start_devialet()
    await _start_domotique()
    await llm.start()
    await tts.start()
    # Warm-up Vosk en arriere-plan (~1.7s) pour que le 1er wake soit instantane
    asyncio.create_task(preload_vosk())
    asyncio.create_task(warmup_nemotron())  # pré-chauffe Nemotron (mode nemotron) -> 1er cmd rapide
    # Connect YouTube ↔ Spotify: pause music when video plays, resume when stops
    youtube.set_music_callbacks(
        pause_fn=music.pause,
        resume_fn=music.resume,
    )
    # Restore Devialet volume after mpv starts (prevents 100% blast)
    youtube.set_volume_callback(devialet.ensure_volume)
    # Pause wake word during video to free CPU for smooth AirPlay audio
    youtube.set_wakeword_callbacks(
        pause_fn=lambda: setattr(wake_detector, 'paused', True),
        resume_fn=lambda: setattr(wake_detector, 'paused', False),
    )
    pipeline_task = asyncio.create_task(voice_pipeline())
    scheduler_task = asyncio.create_task(screen_scheduler())
    touch_wake_task = asyncio.create_task(touch_wake_listener())
    # token_watchdog n'existe que sur le provider Spotify (refresh OAuth).
    watchdog_task = None
    if hasattr(music, "token_watchdog"):
        watchdog_task = asyncio.create_task(music.token_watchdog())
    music_poller_task = asyncio.create_task(music_state_poller())
    # Surveillance des enceintes Bluetooth : bascule auto + reconnexion auto.
    bt_monitor_task = asyncio.create_task(bluetooth_monitor())
    # Surveillance passerelle IA (Mac mini) : pastille gratuit/cloud-payant dans l'UI.
    gateway_monitor_task = asyncio.create_task(gateway_monitor())
    # NE PLUS forcer le volume au démarrage (c'était la cause n°1 des sauts à 50%
    # à chaque redémarrage). On laisse le volume réel du Devialet tel quel.
    # Verrouille seulement la SORTIE CHOISIE comme sink par defaut.
    try:
        sink = await ensure_selected_output()
        logger.info("[AUDIO] Sortie verrouillee -> %s", sink or "(aucune sortie trouvee)")
    except Exception:
        pass
    # Port 8888 redirect for Spotify OAuth callback (registered as http://127.0.0.1:8888/callback)
    proxy_server = await _start_oauth_proxy()
    logger.info("[PI-BOARD] Tous les services demarres")
    yield
    logger.info("[PI-BOARD] Arret...")
    try:
        if hasattr(music, "_player") and music._player:
            await music._player.shutdown()
    except Exception:
        pass
    await audio_capture.stop()
    pipeline_task.cancel()
    scheduler_task.cancel()
    bt_monitor_task.cancel()
    gateway_monitor_task.cancel()
    music_poller_task.cancel()
    touch_wake_task.cancel()
    try:
        await bluetooth.stop_scan()
    except Exception:
        pass
    if watchdog_task:
        watchdog_task.cancel()
    if proxy_server:
        proxy_server.close()
        await proxy_server.wait_closed()


app = FastAPI(title="PI-Board", lifespan=lifespan)

# Expose audio_capture for admin routes (hotword recording)
app.state.audio_capture = audio_capture

# --- Admin panel ---
app.include_router(admin_router)


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    logger.info("[WS] Client connecte (%d total)", len(connected_clients))
    # Un client qui se deconnecte PENDANT le setup (l'UI salon reconnecte souvent)
    # ne doit pas lever une exception non geree -> on protege le 1er envoi aussi.
    try:
        await ws.send_json({"type": "state", "data": assistant_state})
    except Exception:
        pass
    # Config + infos systeme (URL admin du QR) des le connect.
    try:
        _cfg = config.get_all(); _cfg.pop("auth", None)
        await ws.send_json({"type": "config", "data": _cfg})
        await ws.send_json({"type": "system_info", "data": await _system_info()})
    except Exception as e:
        logger.warning("[WS] config/system_info init: %s", e)
    # Send Spotify status on connect (with timeout — don't block WS on rate limits)
    try:
        spotify_status = music.status
        await ws.send_json({"type": "spotify_status", "data": spotify_status})
        dev_status = await asyncio.wait_for(devialet.get_status(), timeout=3)
        vol = dev_status.get("volume") or 50
        await ws.send_json({"type": "volume", "data": vol})
        # Envoie le now-playing courant (le poller librespot ne tourne pas pour Deezer).
        current = await asyncio.wait_for(music.get_current(), timeout=3)
        if current.get("playing"):
            await ws.send_json({"type": "music", "data": current})
            await ws.send_json({"type": "music_queue", "data": await music.get_queue()})
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning("[WS] Statut musique indisponible: %s", e)

    # Le /ws n'est pas authentifie (c'est le canal de l'UI salon locale). Les
    # commandes SENSIBLES (système, écriture de config) ne sont donc acceptées
    # que depuis 127.0.0.1 (l'app flutter-pi tourne sur le Pi). Un appareil
    # distant du LAN doit passer par l'admin web (HTTP authentifie).
    is_local = bool(ws.client and ws.client.host in ("127.0.0.1", "::1", "localhost"))

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except Exception as e:
                logger.warning("[WS] frame ignoree (JSON invalide): %s", e)
                continue
            # Une frame mal formee (non-dict, data non numerique/non-dict, handler
            # qui leve) ne doit JAMAIS tuer la boucle ni fuiter le client : on isole
            # CHAQUE message dans son propre try (defense en profondeur).
            if not isinstance(msg, dict):
                logger.warning("[WS] frame ignoree (pas un objet): %r", msg)
                continue
            logger.info("[WS] Recu: %s", msg)
            if msg.get("type") in _SENSITIVE_WS and not is_local:
                logger.warning("[WS] Commande sensible '%s' refusee (client distant %s)",
                               msg.get("type"), ws.client.host if ws.client else "?")
                continue

            try:
                await _handle_ws_message(ws, msg)
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.warning("[WS] message ignore (%s): %s", msg.get("type"), e)
                continue
    except WebSocketDisconnect:
        pass
    except RuntimeError as e:
        # ws.receive_text() sur une connexion deja fermee leve un RuntimeError
        # ('WebSocket is not connected'), PAS un WebSocketDisconnect -> on traite
        # comme une fin de connexion normale (pas de traceback parasite).
        logger.debug("[WS] connexion terminee: %s", e)
    finally:
        # Retrait UNIQUE du client (garde : list.remove leve si absent).
        if ws in connected_clients:
            connected_clients.remove(ws)
        logger.info("[WS] Client deconnecte (%d restants)", len(connected_clients))


async def _handle_ws_message(ws: WebSocket, msg: dict):
    """Traite UN message WS deja parse (dict). Toute exception est attrapee par
    l'appelant (per-message) -> jamais de fuite de client ni de boucle tuee."""
    global screen_sleeping
    if msg.get("type") == "navigate":
        page = _as_int(msg.get("data", 0), 0)
        await broadcast({"type": "page", "data": page})
    elif msg.get("type") == "simulate_wake":
        asyncio.create_task(on_wake())
    elif msg.get("type") == "simulate_command":
        text = msg.get("data", "")
        async def _run_simulated(t):
            # Chemin debug : route + dispatch DIRECTS, sans toucher le global
            # _pending_handler du pipeline vocal reel (sinon une commande
            # simulee pendant une ecoute STT pourrait voler/ecraser l'intent).
            if assistant_state != "IDLE":
                return
            t = (t or "").strip()
            if not t:
                return
            await broadcast({"type": "transcript", "data": {"text": t, "final": True}})
            try:
                is_yt = youtube.is_playing
            except Exception:
                is_yt = False
            active_ctx = "youtube" if is_yt else memory.domain
            intent, query = route(t, active_context=active_ctx)
            await broadcast({"type": "intent", "data": {"intent": intent, "query": query}})
            await set_state("PROCESSING")
            handler = INTENT_HANDLERS.get(intent, handle_general)
            try:
                await handler(query)
            except Exception as e:
                logger.error("[PIPELINE] Erreur handler simule %s: %s", intent, e)
            await set_state("IDLE")
        _spawn(_run_simulated(text))
    elif msg.get("type") == "music_play_pause":
        # Toggle base sur l'etat reel (pause() de Deezer renvoie toujours paused=True).
        current = await music.get_current()
        if current.get("playing"):
            await music.pause()
            await broadcast({"type": "music", "data": {**current, "playing": False}})
        else:
            await music.resume()
            current = await music.get_current()
            await broadcast({"type": "music", "data": current})
    elif msg.get("type") == "music_pause":
        await music.pause()
        current = await music.get_current()
        await broadcast({"type": "music", "data": {**current, "playing": False}})
    elif msg.get("type") == "music_resume":
        await music.resume()
        current = await music.get_current()
        await broadcast({"type": "music", "data": current})
    elif msg.get("type") == "music_stop":
        # Arret franc : coupe la lecture et vide la file -> UI revient a l'accueil lecteur.
        stopper = getattr(music, "stop", None)
        if stopper:
            await stopper()
        else:
            await music.pause()
        await broadcast({"type": "music", "data": {
            "playing": False, "title": "", "artist": "", "album": "",
            "cover": None, "progress_ms": 0, "duration_ms": 0}})
    elif msg.get("type") == "music_next":
        result = await music.next_track()
        await broadcast({"type": "music", "data": result})
    elif msg.get("type") == "music_prev":
        await music.previous_track()
        current = await music.get_current()
        await broadcast({"type": "music", "data": current})
    elif msg.get("type") == "music_volume":
        await set_output_volume(_as_int(msg.get("data", 50), 50))
    elif msg.get("type") == "music_seek":
        # Barre de progression UI : seek mpv (Deezer). No-op si le
        # provider ne supporte pas (Spotify).
        seeker = getattr(music, "seek", None)
        if seeker:
            await seeker(_as_int(msg.get("data", 0), 0))
    elif msg.get("type") == "music_search":
        query = msg.get("data", "")
        results = await music.search_tracks(query)
        await ws.send_json({"type": "music_search_results", "data": results})
    elif msg.get("type") == "music_play_uri":
        import time as _time
        if hasattr(music, "_poller_skip_until"):
            music._poller_skip_until = _time.time() + 10
        uri = msg.get("data", "")
        await _ensure_bt_output_ready()
        result = await music.play_uri(uri)
        await broadcast({"type": "music", "data": result})
        await asyncio.sleep(1)
        await devialet.ensure_volume()
        queue = await music.get_queue()
        await broadcast({"type": "music_queue", "data": queue})
    elif msg.get("type") == "music_queue":
        queue = await music.get_queue()
        await ws.send_json({"type": "music_queue", "data": queue})
    elif msg.get("type") == "music_progress":
        current = await music.get_current()
        await ws.send_json({"type": "music", "data": current})
    elif msg.get("type") == "music_playlists":
        playlists = await music.get_playlists()
        await ws.send_json({"type": "music_playlists", "data": playlists})
    elif msg.get("type") == "music_play_playlist":
        import time as _time
        if hasattr(music, "_poller_skip_until"):
            music._poller_skip_until = _time.time() + 10
        uri = msg.get("data", "")
        await _ensure_bt_output_ready()
        result = await music.play_playlist(uri)
        await broadcast({"type": "music", "data": result})
        await asyncio.sleep(1)
        await devialet.ensure_volume()
        queue = await music.get_queue()
        await broadcast({"type": "music_queue", "data": queue})
    elif msg.get("type") == "spotify_reauth":
        url = music.get_auth_url() if hasattr(music, "get_auth_url") else None
        if url:
            await ws.send_json({"type": "spotify_reauth_url", "data": url})
    elif msg.get("type") == "spotify_auth_browser":
        # Send auth URL to frontend for display
        auth_url = music.get_auth_url() if hasattr(music, "get_auth_url") else None
        if auth_url:
            await ws.send_json({"type": "spotify_reauth_url", "data": auth_url})
    elif msg.get("type") == "spotify_retry":
        # Retry Spotify connection (e.g. after network issue, no full re-auth)
        await music.start()
        status = music.status
        await broadcast({"type": "spotify_status", "data": status})
        if status == "ok":
            dev_s = await devialet.get_status()
            await broadcast({"type": "volume", "data": dev_s.get("volume") or 50})
    elif msg.get("type") == "youtube_search":
        query = msg.get("data", "")
        if query and len(query) >= 2:
            results = await youtube.search(query, limit=15)
            await ws.send_json({"type": "youtube_results", "data": results})
    elif msg.get("type") == "youtube_select":
        video = msg.get("data")
        video = video if isinstance(video, dict) else {}
        url = video.get("url", "")
        if url:
            async def _resolve_and_notify(v, u):
                # Verrouille la sortie choisie avant la lecture in-Flutter.
                await ensure_selected_output()
                result = await youtube.resolve_for_flutter(u)
                if result.get("playing") and result.get("url"):
                    # L'UI Flutter lit le flux dans la page (gstreamer HW).
                    await broadcast({"type": "youtube_play_url", "data": {
                        "url": result["url"],
                        "title": v.get("title", ""),
                        "channel": v.get("channel", ""),
                        "thumbnail": v.get("thumbnail", ""),
                        "watch_url": u,
                    }})
                else:
                    await broadcast({"type": "youtube_stopped", "data": {"error": result.get("error", "")}})
            asyncio.create_task(_resolve_and_notify(video, url))
    elif msg.get("type") == "youtube_pause":
        pass  # la pause est geree dans l'UI (lecteur in-Flutter)
    elif msg.get("type") == "youtube_stop":
        await youtube.stop_flutter()
        await broadcast({"type": "youtube_stopped", "data": {}})
        # Refresh music state after Spotify resumes
        await asyncio.sleep(1)
        current = await music.get_current()
        if current.get("playing"):
            await broadcast({"type": "music", "data": current})
    elif msg.get("type") == "weather_refresh":
        data = await weather.get_current()
        await ws.send_json({"type": "weather", "data": data})
    elif msg.get("type") == "screen_wake":
        await screen_on()
        screen_sleeping = False
    elif msg.get("type") == "screen_sleep":
        await screen_off()
        screen_sleeping = True
    elif msg.get("type") == "system_shutdown":
        logger.info("[SYSTEM] Shutdown demande par l'utilisateur")
        await ws.send_json({"type": "speaking", "data": "Extinction en cours..."})
        asyncio.create_task(_delayed_shutdown())
    elif msg.get("type") == "system_reboot":
        asyncio.create_task(_delayed_reboot())
    elif msg.get("type") == "system_restart_backend":
        _restart_backend()
    elif msg.get("type") == "system_info":
        await ws.send_json({"type": "system_info", "data": await _system_info()})
    elif msg.get("type") == "config_get":
        _cfg = config.get_all(); _cfg.pop("auth", None)
        await ws.send_json({"type": "config", "data": _cfg})
    elif msg.get("type") == "config_set":
        _d = msg.get("data")
        _d = _d if isinstance(_d, dict) else {}
        _s, _k, _v = _d.get("section"), _d.get("key"), _d.get("value")
        # Liste blanche stricte : jamais 'auth', jamais une clé arbitraire.
        if (_s, _k) in ALLOWED_CONFIG_KEYS:
            # Coercition type/plage : ne JAMAIS persister une valeur invalide
            # ('abc' pour threshold...) qui casserait wakeword.py/llm ensuite.
            _coerce = _CONFIG_COERCE.get((_s, _k))
            if _coerce is not None:
                try:
                    _v = _coerce(_v)
                except (TypeError, ValueError):
                    logger.warning("[WS] config_set valeur invalide %s.%s=%r (ignoree)", _s, _k, _v)
                    return
            config.set(_s, _k, _v)
            _cfg = config.get_all(); _cfg.pop("auth", None)
            await broadcast({"type": "config", "data": _cfg})
        else:
            logger.warning("[WS] config_set refuse (hors liste blanche): %s.%s", _s, _k)
    elif msg.get("type") == "screen_brightness":
        await set_brightness(_as_int(msg.get("data", 100), 100))
    elif msg.get("type") == "domotique_status":
        status = await domotique.get_status()
        await ws.send_json({"type": "domotique_status", "data": status})
    elif msg.get("type") == "domotique_roller":
        d = msg.get("data")
        d = d if isinstance(d, dict) else {}
        dev_id = d.get("id", "")
        action = d.get("action", "")
        if action == "open":
            await domotique.roller_open(dev_id)
        elif action == "close":
            await domotique.roller_close(dev_id)
        elif action == "stop":
            await domotique.roller_stop(dev_id)
        status = await domotique.get_status()
        await broadcast({"type": "domotique_status", "data": status})
    elif msg.get("type") == "domotique_roller_all":
        action = msg.get("data", "")
        if action == "open":
            await domotique.open_all_rollers()
        elif action == "close":
            await domotique.close_all_rollers()
        status = await domotique.get_status()
        await broadcast({"type": "domotique_status", "data": status})
    elif msg.get("type") == "domotique_portail":
        await domotique.trigger_portail()
    elif msg.get("type") == "domotique_plug":
        d = msg.get("data")
        d = d if isinstance(d, dict) else {}
        dev_id = d.get("id", "")
        action = d.get("action", "")
        if action == "on":
            await domotique.plug_on(dev_id)
        elif action == "off":
            await domotique.plug_off(dev_id)
        elif action == "toggle":
            await domotique.plug_toggle(dev_id)
        status = await domotique.get_status()
        await broadcast({"type": "domotique_status", "data": status})
    elif msg.get("type") == "devialet_status":
        status = await devialet.get_status()
        await ws.send_json({"type": "devialet_status", "data": status})
    elif msg.get("type") == "devialet_volume":
        await set_output_volume(_as_int(msg.get("data", 50), 50))
    elif msg.get("type") == "devialet_volume_up":
        await adjust_output_volume(VOLUME_STEP)
    elif msg.get("type") == "devialet_volume_down":
        await adjust_output_volume(-VOLUME_STEP)
    elif msg.get("type") == "devialet_play":
        await devialet.play()
    elif msg.get("type") == "devialet_pause":
        await devialet.pause()
    elif msg.get("type") == "devialet_next":
        await devialet.next_track()
    elif msg.get("type") == "devialet_prev":
        await devialet.previous_track()
    elif msg.get("type") == "devialet_mute":
        await devialet.mute()
    elif msg.get("type") == "devialet_unmute":
        await devialet.unmute()
    elif msg.get("type") == "devialet_power_off":
        asyncio.create_task(handle_devialet_power_off())
    elif msg.get("type") == "devialet_restart":
        asyncio.create_task(handle_devialet_restart())
    elif msg.get("type") == "devialet_night_mode":
        on = bool(msg.get("data", False))
        await devialet.set_night_mode(on)
        status = await devialet.get_status()
        await broadcast({"type": "devialet_status", "data": status})
    elif msg.get("type") == "devialet_eq_preset":
        preset = msg.get("data", "flat")
        await devialet.set_equalizer_preset(preset)
        status = await devialet.get_status()
        await broadcast({"type": "devialet_status", "data": status})
    elif msg.get("type") == "audio_sinks":
        sinks = await _get_audio_sinks()
        await ws.send_json({"type": "audio_sinks", "data": sinks})
    elif msg.get("type") == "audio_set_sink":
        global _manual_sink_switch_inflight
        sink_name = msg.get("data", "")
        if sink_name:
            # Garde anti-course : empeche bluetooth_monitor de restaurer le Devialet
            # sur un idle-drop bref de l'enceinte pendant ce connect+set utilisateur.
            _manual_sink_switch_inflight = True
            try:
                # Enceinte BT choisie mais deconnectee -> on la connecte d'abord
                # (avec re-essais), puis on bascule dessus.
                mac = _mac_from_bluez_sink(sink_name)
                ok_select = True
                if mac and not await find_bluez_sink(mac):
                    _bt_user_disconnected.discard(mac)
                    ok, err = await bluetooth.connect(mac)
                    # Le sink BT peut mettre quelques secondes a apparaitre apres
                    # connexion (cf _ensure_bt_output_ready) -> on attend.
                    real = None
                    if ok:
                        for _ in range(8):
                            real = await find_bluez_sink(mac)
                            if real:
                                break
                            await asyncio.sleep(1)
                    if real:
                        sink_name = real
                    else:
                        ok_select = False
                        await broadcast({"type": "bt_action_result", "data": {
                            "ok": False, "op": "bt_connect", "mac": mac,
                            "error": err or "connexion impossible"}})
                if ok_select:
                    result = await _set_audio_sink(sink_name)
                    # BROADCAST (pas send_json) : tous les écrans reflètent la sortie.
                    await broadcast({"type": "audio_sink_changed", "data": result})
                await broadcast({"type": "audio_sinks", "data": await _get_audio_sinks()})
            finally:
                _manual_sink_switch_inflight = False
    elif msg.get("type") == "bt_devices":
        await ws.send_json({"type": "bt_devices", "data": await _bt_state()})
    elif msg.get("type") == "bt_scan":
        _d = msg.get("data")
        action = (_d if isinstance(_d, dict) else {}).get("action", "start")
        if action == "start":
            if not bluetooth.is_scanning():
                asyncio.create_task(_bt_scan_task())
        else:
            await bluetooth.stop_scan()
            await broadcast({"type": "bt_devices", "data": await _bt_state()})
    elif msg.get("type") in ("bt_pair", "bt_connect", "bt_disconnect", "bt_forget"):
        _d = msg.get("data")
        mac = (_d if isinstance(_d, dict) else {}).get("mac", "")
        if mac:
            asyncio.create_task(_bt_action(msg["type"], mac))
    elif msg.get("type") == "cameras_list":
        cams = await cameras.get_cameras()
        await ws.send_json({"type": "cameras_list", "data": cams})
    elif msg.get("type") == "cameras_snapshots":
        snaps = await cameras.get_all_snapshots()
        await ws.send_json({"type": "cameras_snapshots", "data": snaps})
    elif msg.get("type") == "camera_snapshot":
        cam_id = msg.get("data", "")
        snap = await cameras.get_snapshot(cam_id)
        await ws.send_json({"type": "camera_snapshot", "data": {"id": cam_id, "snapshot": snap}})



# --- REST endpoints ---

@app.get("/deezer/stream/{track_id}")
async def deezer_stream(track_id: str, fmt: str = DEEZER_QUALITY):
    """Sert le flux audio Deezer dechiffre (mpv lit cette URL via UPnP/local).

    Resout l'URL CDN chiffree + la cle Blowfish puis stream le dechiffrement
    a la volee. `fmt` optionnel (FLAC | MP3_320 | MP3_128), defaut DEEZER_QUALITY.
    """
    from services.music import deezer_stream as _ds
    info = await asyncio.get_event_loop().run_in_executor(None, _ds.resolve_stream, track_id, fmt)
    if not info:
        return Response(status_code=404)
    return StreamingResponse(
        _ds.decrypt_aiter(info["url"], info["key"]),
        media_type=info["mime"],
    )


@app.get("/api/weather")
async def api_weather():
    return await weather.get_current()


@app.get("/api/spotify/current")
async def api_spotify_current():
    return await music.get_current()


@app.get("/api/spotify/status")
async def api_spotify_status():
    return {"status": music.status}


@app.get("/api/spotify/reauth")
async def api_spotify_reauth():
    """Smart Spotify auth page — works from phone or PC."""
    url = music.get_auth_url() if hasattr(music, "get_auth_url") else None
    if not url:
        return JSONResponse({"error": "Spotify non configure"}, status_code=400)
    from fastapi.responses import HTMLResponse
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>
* {{ box-sizing: border-box; }}
body {{ background: #060610; color: #f0f0f0; font-family: -apple-system, Inter, sans-serif;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 100vh; margin: 0; padding: 20px; gap: 16px; }}
h2 {{ font-size: 20px; color: #1DB954; margin: 0; }}
p {{ font-size: 13px; color: #888; margin: 0; text-align: center; }}
.btn {{ display: inline-block; background: #1DB954; color: #000; font-weight: 700;
  padding: 14px 28px; border-radius: 30px; text-decoration: none; font-size: 15px; }}
.btn:active {{ opacity: 0.8; }}
.step {{ background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
  border-radius: 12px; padding: 16px; width: 100%; max-width: 400px; }}
.step-num {{ display: inline-block; width: 24px; height: 24px; background: #7C6FFF;
  color: #fff; border-radius: 50%; text-align: center; line-height: 24px; font-size: 12px;
  font-weight: 700; margin-right: 8px; }}
input {{ width: 100%; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15);
  color: #f0f0f0; padding: 10px 12px; border-radius: 8px; font-size: 13px; margin-top: 8px; }}
.send {{ background: #7C6FFF; color: #fff; border: none; padding: 10px 20px;
  border-radius: 8px; font-weight: 600; font-size: 13px; margin-top: 8px; cursor: pointer; }}
.status {{ font-size: 12px; color: #888; margin-top: 8px; }}
.ok {{ color: #1DB954; font-size: 16px; }}
#result {{ display: none; }}
</style>
</head><body>
<h2>Connexion Spotify</h2>

<div id="steps">
  <div class="step">
    <p><span class="step-num">1</span> Appuyez pour vous connecter a Spotify</p>
    <br>
    <a class="btn" href="{url}" target="_blank">Ouvrir Spotify</a>
  </div>

  <div class="step" style="margin-top:12px">
    <p><span class="step-num">2</span> Apres autorisation, la page affichera une erreur.
    <br>Copiez l'URL complete de la barre d'adresse et collez-la ici :</p>
    <input id="cb" type="text" placeholder="http://127.0.0.1:8888/callback?code=..." autocomplete="off">
    <button class="send" onclick="sendCode()">Envoyer</button>
    <div class="status" id="status"></div>
  </div>
</div>

<div id="result">
  <span class="ok">&#10004;</span>
  <h2>Spotify connecte !</h2>
  <p>Vous pouvez fermer cette page</p>
</div>

<script>
function sendCode() {{
  var url = document.getElementById('cb').value.trim();
  var match = url.match(/code=([^&]+)/);
  if (!match) {{ document.getElementById('status').textContent = 'URL invalide — doit contenir ?code='; return; }}
  var code = match[1];
  document.getElementById('status').textContent = 'Envoi...';
  fetch('/api/spotify/callback?code=' + encodeURIComponent(code))
    .then(r => r.text())
    .then(t => {{
      if (t.includes('connecte')) {{
        document.getElementById('steps').style.display = 'none';
        document.getElementById('result').style.display = 'flex';
        document.getElementById('result').style.flexDirection = 'column';
        document.getElementById('result').style.alignItems = 'center';
        document.getElementById('result').style.gap = '12px';
      }} else {{
        document.getElementById('status').textContent = 'Erreur: ' + t.substring(0, 100);
      }}
    }})
    .catch(e => {{ document.getElementById('status').textContent = 'Erreur reseau: ' + e; }});
}}

// Auto-check if already connected (polling)
setInterval(function() {{
  fetch('/api/spotify/status').then(r => r.json()).then(d => {{
    if (d.status === 'ok') {{
      document.getElementById('steps').style.display = 'none';
      document.getElementById('result').style.display = 'flex';
      document.getElementById('result').style.flexDirection = 'column';
      document.getElementById('result').style.alignItems = 'center';
      document.getElementById('result').style.gap = '12px';
    }}
  }}).catch(function(){{}});
}}, 3000);
</script>
</body></html>"""
    return HTMLResponse(html)


@app.get("/api/spotify/callback")
async def api_spotify_callback(code: str = ""):
    """Handle Spotify OAuth callback with styled result page."""
    from fastapi.responses import HTMLResponse
    if not code:
        return JSONResponse({"error": "Code manquant"}, status_code=400)
    if not hasattr(music, "handle_callback"):
        return JSONResponse({"error": "Provider non-Spotify"}, status_code=400)
    success = await music.handle_callback(code)
    if success:
        icon = "&#10004;"
        color = "#1DB954"
        title = "Spotify connecte !"
        detail = "Retour a l'interface..."
    else:
        icon = "&#10008;"
        color = "#ff6b6b"
        title = "Echec de connexion"
        detail = "Retour automatique dans 3 secondes"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>
body {{ background: #0a0a0f; color: #f0f0f0; font-family: Inter, sans-serif;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100vh; margin: 0; gap: 16px; }}
.icon {{ font-size: 48px; color: {color}; }}
h2 {{ font-size: 20px; color: {color}; margin: 0; }}
p {{ font-size: 13px; color: #888; margin: 0; }}
</style>
</head><body>
<span class="icon">{icon}</span>
<h2>{title}</h2>
<p>{detail}</p>
<script>setTimeout(function() {{ window.location.href = "/"; }}, 2000);</script>
</body></html>"""
    return HTMLResponse(html)


@app.get("/callback")
async def legacy_spotify_callback(code: str = ""):
    """Legacy redirect URI (http://127.0.0.1:8888/callback -> port 8000) — forward to real handler."""
    return await api_spotify_callback(code=code)


@app.api_route("/api/youtube/audio-proxy", methods=["GET", "HEAD"])
async def api_youtube_audio_proxy():
    """Proxy YouTube audio stream for UPnP playback (Devialet can't access HTTPS googlevideo)."""
    from starlette.requests import Request
    proxy_url = getattr(youtube, '_current_audio_proxy_url', None)
    if not proxy_url:
        return JSONResponse({"error": "No audio stream"}, status_code=404)

    import httpx

    async def _stream():
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", proxy_url, timeout=120) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    return StreamingResponse(_stream(), media_type="audio/ogg")


# Serve UPnP audio files (TTS, etc.)
upnp_audio_dir = Path(__file__).parent / ".." / "frontend" / "dist" / "upnp_audio"
upnp_audio_dir.mkdir(parents=True, exist_ok=True)
app.mount("/upnp_audio", StaticFiles(directory=upnp_audio_dir), name="upnp-audio")


@app.get("/api/cameras/{camera_id}/stream")
async def api_camera_stream(camera_id: str):
    return StreamingResponse(
        cameras.stream_mjpeg(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# --- Serve admin frontend ---

admin_static = Path(__file__).parent / "admin" / "static"
if admin_static.exists() and (admin_static / "assets").exists():
    app.mount("/admin/assets", StaticFiles(directory=admin_static / "assets"), name="admin-assets")


@app.get("/admin/{full_path:path}")
async def serve_admin(full_path: str):
    # Don't intercept API or asset routes
    if full_path.startswith("api/") or full_path.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Not found")
    if admin_static.exists():
        file = admin_static / full_path
        if file.exists() and file.is_file():
            return FileResponse(file)
        index = admin_static / "index.html"
        if index.exists():
            return FileResponse(index)
    return JSONResponse({"error": "Admin UI not built"}, status_code=404)


# --- Serve main frontend (MUST be last — catch-all route) ---

frontend_path = Path(FRONTEND_BUILD_DIR)
if frontend_path.exists():
    if (frontend_path / "assets").exists():
        app.mount("/assets", StaticFiles(directory=frontend_path / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file = frontend_path / full_path
        if file.exists() and file.is_file():
            return FileResponse(file)
        return FileResponse(frontend_path / "index.html")


if __name__ == "__main__":
    import uvicorn
    import socket

    # Create socket with SO_REUSEADDR to allow quick restart
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", BACKEND_PORT))
    sock.set_inheritable(True)

    # NE PAS reutiliser le nom 'config' (= singleton ConfigManager importe L21,
    # utilise par les handlers). On nomme la config uvicorn a part.
    uvicorn_config = uvicorn.Config("main:app", host="0.0.0.0", port=BACKEND_PORT)
    server = uvicorn.Server(uvicorn_config)

    import asyncio
    asyncio.run(server.serve(sockets=[sock]))
