"""LAN Voice Gateway — cerveau vocal LOCAL et GRATUIT sur le Mac mini.

Expose sur le LAN (port 8765, auth par token) une petite API qui encapsule :
  - Ollama / Gemma 4 12B QAT (127.0.0.1:11434, think:false)  -> routeur d'intentions + chat court
  - Voxtral 4B TTS MLX local (modele charge WARM en memoire) -> WAV 24 kHz

Le Raspberry Pi (PI-Board) reste client leger : il envoie du texte, recoit
de l'intention JSON et/ou un WAV. Aucune API payante sur le chemin nominal.

Tourne DANS le venv voxtral-tts (.venv) pour reutiliser mlx_audio et garder le
modele TTS chaud. Ne modifie jamais ~/.hermes/hermes.json."""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lan-voice-gateway")

# --- Config (.env) -----------------------------------------------------------
HERE = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
except Exception:
    pass
TOKEN = os.getenv("LAN_VOICE_TOKEN", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4-12b-qat-q4-k-xl")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "60"))
KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
ALLOWED_IPS = {ip.strip() for ip in os.getenv("ALLOWED_IPS", "").split(",") if ip.strip()}

TTS_BASE = Path(os.getenv("VOXTRAL_TTS_BASE",
                          os.path.expanduser("~/.hermes/workspace/voxtral-tts")))
TTS_MODEL_DIR = TTS_BASE / "models" / "Voxtral-4B-TTS-2603-mlx-4bit"
TTS_VOICE_DEFAULT = os.getenv("TTS_VOICE_DEFAULT", "fr_female")
TTS_TEMP = float(os.getenv("TTS_TEMPERATURE", "0.7"))
TTS_SR = 24000
CACHE_DIR = HERE / "var" / "tts-cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Phrases frequentes pre-generees au demarrage (cache chaud -> reponse instantanee)
FREQUENT_PHRASES = [
    "Je lance.", "C'est fait.", "Je n'ai pas compris.", "J'allume.", "J'éteins.",
    "D'accord.", "Voilà.", "Je mets en pause.", "Musique suivante.",
    "Je n'ai pas trouvé cette musique.", "Désolé, une erreur est survenue.",
]

# Modele TTS charge une seule fois (warm)
_tts_model = None

# --- Routeur d'intentions (system prompt) ------------------------------------
ROUTER_SYSTEM = """Tu es le routeur d'un assistant vocal local français.
Réponds uniquement en JSON valide compact. Pas de markdown. Pas d'explication. Pas de texte hors JSON.

Schéma obligatoire :
{"intent": string, "confidence": number, "entities": object, "speak": string}

Intentions autorisées :
music.play, music.pause, music.next, music.volume_set,
home.light_on, home.light_off, timer.set, reminder.add, chat.small_answer, unknown

Règles :
- "mets/joue/lance <musique/artiste/titre>" -> intent=music.play, entities.query=requête musicale nettoyée.
- "pause/stop/arrête (la musique)" -> music.pause. "suivant/passe" -> music.next.
- "monte/baisse/règle le volume (à N)" -> music.volume_set, entities.volume=N (0-100).
- "allume/éteins la lumière (de la pièce)" -> home.light_on/off, entities.room.
- "minuteur/timer de N minutes" -> timer.set, entities.minutes=N.
- Question générale courte -> chat.small_answer avec la réponse dans speak (max 1 phrase).
- speak: réponse vocale naturelle, max 8 mots. Si ambigu: unknown.

Exemples :
{"intent":"music.play","confidence":0.95,"entities":{"query":"Phil Collins"},"speak":"Je lance Phil Collins."}
{"intent":"music.pause","confidence":0.97,"entities":{},"speak":"Pause."}
{"intent":"music.volume_set","confidence":0.95,"entities":{"volume":40},"speak":"Volume à 40."}
{"intent":"home.light_on","confidence":0.93,"entities":{"room":"salon"},"speak":"J'allume le salon."}"""

CHAT_SYSTEM = """Tu es un assistant vocal local français. Réponds en UNE phrase courte,
naturelle, parlée (max 2 phrases). Pas de markdown, pas de liste, pas d'emoji."""

# Fast-path déterministe (évite de réveiller le LLM pour les commandes triviales)
_RE_MUSIC = re.compile(r"^\s*(?:mets?|met|joue|lance)\s+(?:moi\s+)?(?:de\s+la\s+|du\s+|la\s+|le\s+|des\s+)?"
                       r"(?:musique\s+(?:de\s+|du\s+|d['’]\s*)?)?(.+?)\s*$", re.I)
_RE_PAUSE = re.compile(r"^\s*(?:pause|stop|arrê?te|arrete)(?:\s+la\s+musique)?\s*$", re.I)
_RE_NEXT = re.compile(r"^\s*(?:suivant|passe|next|chanson\s+suivante|musique\s+suivante)\s*$", re.I)


def _fast_intent(text: str):
    if _RE_PAUSE.match(text):
        return {"intent": "music.pause", "confidence": 0.99, "entities": {}, "speak": "Pause."}
    if _RE_NEXT.match(text):
        return {"intent": "music.next", "confidence": 0.99, "entities": {}, "speak": "Suivant."}
    m = _RE_MUSIC.match(text)
    if m:
        q = m.group(1).strip()
        # éviter de capter "la lumière ..." etc. via le fast-path musique
        if not re.search(r"\b(lumi[eè]re|volet|portail|minuteur|timer|volume)\b", q, re.I):
            # "lance/joue la musique" sans titre -> requête vide => Flow Deezer côté Pi
            if q.lower() in {"musique", "de la musique", "un truc", "quelque chose",
                             "n'importe quoi", "n’importe quoi", "ce que tu veux"}:
                q = ""
            return {"intent": "music.play", "confidence": 0.9,
                    "entities": {"query": q},
                    "speak": "Je lance la musique." if not q else f"Je lance {q}."}
    return None


# --- Ollama ------------------------------------------------------------------
def _ollama_chat_sync(system: str, user: str, num_predict: int, temperature: float,
                      fmt: str | None = None) -> str:
    payload = {
        "model": OLLAMA_MODEL, "think": False, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "options": {"temperature": temperature, "num_predict": num_predict, "top_p": 0.8},
        "keep_alive": KEEP_ALIVE,
    }
    if fmt:
        payload["format"] = fmt  # "json" -> mode JSON natif Ollama
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as r:
        resp = json.loads(r.read())
    # On ne lit QUE message.content (jamais 'thinking').
    return (resp.get("message", {}) or {}).get("content", "") or ""


async def ollama_chat(system: str, user: str, num_predict: int = 160,
                      temperature: float = 0.0, fmt: str | None = None) -> str:
    return await asyncio.to_thread(_ollama_chat_sync, system, user, num_predict, temperature, fmt)


def _ollama_up() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


_JSON_RE = re.compile(r"\{.*\}", re.S)


def _extract_json(s: str):
    s = re.sub(r"<think>.*?</think>", "", s or "", flags=re.S)
    s = s.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    m = _JSON_RE.search(s)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


# Nettoyage de la sortie modèle. Retire le bloc <think>…</think> (reasoning) ET
# les tokens spéciaux Gemma qui fuient parfois ("<image|>", "<start_of_image>",
# "<unused42>"…) — sinon le TTS les lit à voix haute. Remplace par une espace
# puis normalise (insécables et doubles espaces).
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_SPECIAL_TOK_RE = re.compile(r"<(?:start_of_image|end_of_image|image|unused\d+)[^>]*>|<[^<>\s]*\|>")


def _clean_text(raw: str) -> str:
    s = _THINK_RE.sub("", raw or "")
    s = _SPECIAL_TOK_RE.sub(" ", s)
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def _norm_intent(obj: dict, fallback_speak: str = "") -> dict:
    allowed = {"music.play", "music.pause", "music.next", "music.volume_set",
               "home.light_on", "home.light_off", "timer.set", "reminder.add",
               "chat.small_answer", "unknown"}
    if not isinstance(obj, dict):
        obj = {}
    intent = obj.get("intent")
    if intent not in allowed:
        intent = "unknown"
    # confidence : cast tolérant (LLM peut renvoyer 'high', null, liste...) + clamp [0,1]
    try:
        conf = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    # entities doit être un dict (le Pi fait entities.get('query'))
    entities = obj.get("entities")
    if not isinstance(entities, dict):
        entities = {}
    # speak doit être une str non vide (sinon le TTS casse côté Pi) ; on nettoie
    # les tokens spéciaux Gemma qui peuvent fuiter dans ce champ parlé.
    speak_val = obj.get("speak")
    speak = _clean_text(speak_val) if isinstance(speak_val, str) else ""
    if not speak:
        speak = fallback_speak
    return {
        "intent": intent,
        "confidence": conf,
        "entities": entities,
        "speak": speak,
    }


# --- TTS (Voxtral MLX warm) --------------------------------------------------
def _tts_generate_sync(text: str, voice: str) -> bytes:
    key = hashlib.sha256(f"{voice}|{TTS_TEMP}|{text}".encode("utf-8")).hexdigest()[:32]
    out = CACHE_DIR / f"{key}.wav"
    if out.exists() and out.stat().st_size > 0:
        return out.read_bytes()
    segs = _tts_model.generate(text=text, voice=voice, temperature=TTS_TEMP)
    audio = [np.asarray(s.audio).reshape(-1) for s in segs]
    a = np.concatenate(audio) if audio else np.zeros(1, dtype=np.float32)
    sf.write(str(out), a, TTS_SR, subtype="PCM_16")
    return out.read_bytes()


async def tts_generate(text: str, voice: str) -> bytes:
    return await asyncio.to_thread(_tts_generate_sync, text, voice)


# --- Lifespan : warm-up ------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tts_model
    logger.info("Chargement du modele TTS Voxtral (warm)...")
    t0 = time.time()
    from mlx_audio.tts.utils import load  # importe dans le venv voxtral-tts
    _tts_model = await asyncio.to_thread(load, str(TTS_MODEL_DIR))
    logger.info("TTS chargé en %.1fs", time.time() - t0)
    # Préchauffe Ollama (mini requête) + cache des phrases fréquentes
    try:
        await ollama_chat("Réponds OK.", "ping", num_predict=4)
        logger.info("Ollama préchauffé (%s)", OLLAMA_MODEL)
    except Exception as e:
        logger.warning("Préchauffe Ollama échouée: %s", e)
    for ph in FREQUENT_PHRASES:
        try:
            await tts_generate(ph, TTS_VOICE_DEFAULT)
        except Exception as e:
            logger.warning("Cache TTS '%s' échoué: %s", ph, e)
    logger.info("Gateway prêt (cache TTS: %d phrases)", len(FREQUENT_PHRASES))
    yield


app = FastAPI(title="LAN Voice Gateway", lifespan=lifespan)


# --- Auth --------------------------------------------------------------------
async def auth(request: Request, x_lan_voice_token: str = Header(default="")):
    if ALLOWED_IPS:
        client = request.client.host if request.client else ""
        if client not in ALLOWED_IPS:
            raise HTTPException(status_code=403, detail="IP non autorisée")
    if not TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    if not hmac.compare_digest(x_lan_voice_token or "", TOKEN):
        raise HTTPException(status_code=401, detail="Token invalide")
    return True


# --- Modèles I/O -------------------------------------------------------------
class IntentIn(BaseModel):
    text: str
    context: dict | None = None


class ChatIn(BaseModel):
    text: str


class CompleteIn(BaseModel):
    system: str = ""
    user: str
    max_tokens: int = 200
    temperature: float = 0.2
    json_mode: bool = False


class TTSIn(BaseModel):
    text: str
    voice: str | None = None


class VoiceCmdIn(BaseModel):
    text: str
    return_audio: bool = False


# --- Endpoints ---------------------------------------------------------------
@app.get("/health")
async def health():
    return {"ok": True, "ollama": await asyncio.to_thread(_ollama_up), "model": OLLAMA_MODEL,
            "tts": "voxtral" if _tts_model is not None else "loading",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


@app.post("/llm/intent")
async def llm_intent(body: IntentIn, _=Depends(auth)):
    text = (body.text or "").strip()
    fast = _fast_intent(text)
    if fast:
        return fast
    raw = await ollama_chat(ROUTER_SYSTEM, text, num_predict=160, temperature=0.0)
    obj = _extract_json(raw)
    return _norm_intent(obj or {}, fallback_speak="")


@app.post("/llm/chat")
async def llm_chat(body: ChatIn, _=Depends(auth)):
    raw = await ollama_chat(CHAT_SYSTEM, (body.text or "").strip(), num_predict=200, temperature=0.3)
    return {"text": _clean_text(raw)}


@app.post("/llm/complete")
async def llm_complete(body: CompleteIn, _=Depends(auth)):
    """Complétion générique (system+user -> texte). json_mode=true -> JSON natif Ollama.
    Sert les besoins spécialisés du Pi (playlist, identification, etc.)."""
    raw = await ollama_chat(body.system, (body.user or "").strip(),
                            num_predict=body.max_tokens, temperature=body.temperature,
                            fmt="json" if body.json_mode else None)
    return {"text": _clean_text(raw)}


@app.post("/tts")
async def tts(body: TTSIn, _=Depends(auth)):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="texte vide")
    voice = body.voice or TTS_VOICE_DEFAULT
    wav = await tts_generate(text, voice)
    if not wav:
        raise HTTPException(status_code=500, detail="TTS vide")
    return Response(content=wav, media_type="audio/wav")


@app.post("/voice-command")
async def voice_command(body: VoiceCmdIn, _=Depends(auth)):
    """Intent + speak. L'exécution de l'action vit côté Pi (stack musique/domotique)."""
    intent = await llm_intent(IntentIn(text=body.text))  # réutilise fast-path + LLM
    out = {"intent": intent, "action_result": None, "speak": intent.get("speak", "")}
    return JSONResponse(out)
