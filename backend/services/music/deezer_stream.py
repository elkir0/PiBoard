"""Source unique de verite pour Deezer : auth ARL + resolution de stream +
dechiffrement Blowfish.

Partage par DEUX consommateurs :
  - la route FastAPI `GET /deezer/stream/{track_id}?fmt=FLAC` (main.py) qui
    sert l'audio dechiffre a mpv via StreamingResponse ;
  - `DeezerProvider` qui reutilise le meme client logge pour la recherche,
    les playlists et la radio.

deezer-py est SYNCHRONE (requests). Le backend etant async, tout appel
bloquant doit passer par `run_in_executor` cote appelant ; ce module expose
donc un `get_client()` sync ET un `ensure_login()` async.

Robustesse : aucune fonction ne crashe le main loop. Pas d'ARL / login KO ->
mode degrade (client None, logge), jamais d'exception remontee.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading

import httpx

logger = logging.getLogger(__name__)

# --- Config (import defensif : le module doit s'importer meme si config.py
#     n'expose pas encore ces cles -> mode degrade no_credentials) ---
try:
    from config import DEEZER_ARL, DEEZER_QUALITY  # type: ignore
except Exception:  # pragma: no cover - config sans cles Deezer
    DEEZER_ARL = ""
    DEEZER_QUALITY = "FLAC"

try:
    import deezer  # deezer-py 1.3.7 (import "deezer")
    HAS_DEEZER = True
except ImportError:
    HAS_DEEZER = False
    logger.warning("[DEEZER] deezer-py non disponible")

try:
    from Crypto.Cipher import Blowfish
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    logger.warning("[DEEZER] pycryptodome non disponible — pas de dechiffrement")

# --- Constantes crypto (verifiees live -> produit b"fLaC") ---
SECRET = "g4el58wc0zvf9na1"
IV = b"\x00\x01\x02\x03\x04\x05\x06\x07"
CHUNK_SIZE = 2048

# UA navigateur pour ne pas se faire jeter par le CDN dzcdn.net
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Formats supportes -> (extension logique, mime). Ordre de fallback gere plus bas.
_MIME = {"FLAC": "audio/flac", "MP3_320": "audio/mpeg", "MP3_128": "audio/mpeg"}

# --- Singleton client logge (acces concurrent route-stream + provider) ---
_client = None  # type: ignore
_client_lock = threading.Lock()


def bf_key(sng_id: str) -> bytes:
    """Derive la cle Blowfish a partir du SNG_ID (post-fallback !)."""
    m = hashlib.md5(str(sng_id).encode()).hexdigest()
    key = "".join(
        chr(ord(m[i]) ^ ord(m[i + 16]) ^ ord(SECRET[i])) for i in range(16)
    ).encode("ascii")
    return key


def decrypt_chunk(chunk: bytes, key: bytes) -> bytes:
    """Dechiffre un bloc de 2048 octets (Blowfish CBC). Verbatim verifie."""
    return Blowfish.new(key, Blowfish.MODE_CBC, IV).decrypt(chunk)


def get_client():
    """Singleton client Deezer logge via ARL. None si indisponible / login KO.

    Re-tente le login si la session a saute (current_user vide).
    """
    global _client
    if not HAS_DEEZER:
        return None
    if not DEEZER_ARL:
        logger.info("[DEEZER] Mode mock (pas d'ARL)")
        return None

    # Un seul thread (re)login a la fois ; les autres reutilisent le client.
    with _client_lock:
        # Session deja active et valide ?
        if _client is not None:
            try:
                if _client.current_user and _client.current_user.get("id"):
                    return _client
            except Exception:
                pass
            logger.warning("[DEEZER] Session perdue — re-login")
            _client = None

        try:
            dz = deezer.Deezer()
            ok = dz.login_via_arl(DEEZER_ARL)
            if not ok or not getattr(dz, "current_user", None) or not dz.current_user.get("id"):
                logger.error("[DEEZER] Login ARL echoue (ARL invalide/expire ?)")
                _client = None
                return None
            _client = dz
            logger.info("[DEEZER] Connecte (user %s)", dz.current_user.get("id"))
            return _client
        except Exception as e:
            logger.error("[DEEZER] Erreur login: %s", e)
            _client = None
            return None


async def ensure_login():
    """Version async : execute le login bloquant dans l'executor."""
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, get_client)
    except Exception as e:
        logger.error("[DEEZER] Erreur ensure_login: %s", e)
        return None


def resolve_stream(track_id: str, quality: str = "FLAC") -> dict | None:
    """Resout l'URL CDN chiffree + la cle Blowfish pour une piste.

    Retourne {url, key (bytes), fmt, size (int), mime} ou None en cas d'echec.
    La cle utilise le SNG_ID POST-FALLBACK (get_track_with_fallback), pas l'id
    de recherche. Fallback de format : demande -> MP3_320 -> MP3_128.
    """
    dz = get_client()
    if dz is None:
        return None

    quality = (quality or "FLAC").upper()
    if quality not in _MIME:
        quality = "FLAC"

    try:
        track = dz.gw.get_track_with_fallback(track_id)
    except Exception as e:
        logger.error("[DEEZER] Erreur get_track_with_fallback(%s): %s", track_id, e)
        return None

    if not track:
        logger.warning("[DEEZER] Piste introuvable: %s", track_id)
        return None

    token = track.get("TRACK_TOKEN")
    real_id = track.get("SNG_ID") or track_id  # id post-fallback (cle Blowfish)
    if not token:
        logger.warning("[DEEZER] Pas de TRACK_TOKEN pour %s", track_id)
        return None

    # Ordre d'essai : format demande puis fallback par qualite decroissante.
    order = [quality]
    for f in ("MP3_320", "MP3_128"):
        if f not in order:
            order.append(f)

    for fmt in order:
        try:
            url = dz.get_track_url(token, fmt)
        except Exception as e:
            logger.warning("[DEEZER] get_track_url(%s) KO: %s", fmt, e)
            url = None
        if not url:
            continue
        size = 0
        try:
            size = int(track.get(f"FILESIZE_{fmt}", 0) or 0)
        except (TypeError, ValueError):
            size = 0
        logger.info("[DEEZER] Stream resolu %s en %s (%d octets)", real_id, fmt, size)
        return {
            "url": url,
            "key": bf_key(real_id),
            "fmt": fmt,
            "size": size,
            "mime": _MIME[fmt],
        }

    logger.error("[DEEZER] Aucune URL de stream pour %s (tous formats KO)", track_id)
    return None


async def decrypt_aiter(url: str, key: bytes):
    """Version async (httpx) du flux dechiffre : ne bloque AUCUN thread pour la
    duree de la chanson.

    httpx renvoie des morceaux de taille variable -> on rebufferise en blocs de
    2048 o pour respecter l'index ABSOLU du schema Blowfish-CBC-stripe.
    """
    headers = {"User-Agent": USER_AGENT}
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                resp.raise_for_status()
                buf = bytearray()
                i = 0
                async for chunk in resp.aiter_bytes():
                    buf += chunk
                    while len(buf) >= CHUNK_SIZE:
                        block = bytes(buf[:CHUNK_SIZE])
                        del buf[:CHUNK_SIZE]
                        if i % 3 == 0 and HAS_CRYPTO:
                            try:
                                yield decrypt_chunk(block, key)
                            except Exception:
                                yield block
                        else:
                            yield block
                        i += 1
                if buf:
                    yield bytes(buf)  # dernier bloc partiel (non chiffre)
    except Exception as e:
        logger.error("[DEEZER] Erreur stream async: %s", e)
