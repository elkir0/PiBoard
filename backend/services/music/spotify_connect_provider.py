"""Fournisseur musical SPOTIFY CONNECT — récepteur **go-librespot**.

Modèle INVERSÉ par rapport aux autres providers : ici le Pi est un **point de
lecture Spotify Connect** (il apparaît comme « PiBoard » dans l'app Spotify de
l'utilisateur, via zeroconf). C'est le **téléphone qui choisit** quoi jouer ;
go-librespot décode le flux et le sort directement vers PipeWire -> AirPlay ->
enceintes. PI-Board ne fait que **lire l'état (now-playing)** et **piloter le
transport** (pause / lecture / suivant / précédent / seek) via l'API HTTP locale
de go-librespot.

Conséquence : la **recherche / lecture par URI / playlists** n'ont pas de sens en
mode récepteur (c'est l'app Spotify qui pilote). Ces méthodes renvoient un dict
dégradé invitant à utiliser l'app — sans jamais crasher.

Prérequis : un binaire **go-librespot** lancé sur le LAN avec son API HTTP activée
(`server.enabled: true`) et un compte **Spotify Premium** (le Connect zeroconf
exige Premium). URL de l'API : `GO_LIBRESPOT_API_URL` (défaut http://127.0.0.1:3678).

Implémente l'interface commune `MusicProvider` (voir base.py). Tout est async ;
aucune méthode ne lève — échec -> log `[SPOTIFY-CONNECT] ...` + dict dégradé.
"""
from __future__ import annotations

import logging

import httpx

from .base import MusicProvider

logger = logging.getLogger(__name__)

# Réponse standard quand une action n'a pas de sens en mode récepteur.
_RECEIVER_HINT = "Choisis « PiBoard » dans ton app Spotify pour lancer la lecture."


class SpotifyConnectProvider(MusicProvider):
    """Récepteur Spotify Connect (go-librespot) : now-playing + transport."""

    def __init__(self) -> None:
        super().__init__()
        try:
            from config import GO_LIBRESPOT_API_URL
        except Exception:
            GO_LIBRESPOT_API_URL = ""
        self._base = (GO_LIBRESPOT_API_URL or "http://127.0.0.1:3678").rstrip("/")
        self._reachable = False

    # ------------------------------------------------------------------ HTTP
    async def _get(self, path: str) -> dict | None:
        """GET l'API go-librespot. Renvoie le JSON, {} si joignable mais sans
        contenu (HTTP 204 = aucune session Spotify active / idle), ou None si
        injoignable (binaire pas lancé). On distingue ainsi « idle » de « down »."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(4)) as c:
                r = await c.get(self._base + path)
                r.raise_for_status()
                if r.status_code == 204 or not r.content:
                    return {}
                return r.json()
        except Exception as e:
            logger.debug("[SPOTIFY-CONNECT] GET %s: %s", path, e)
            return None

    async def _post(self, path: str, body: dict | None = None) -> bool:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(4)) as c:
                r = await c.post(self._base + path, json=body or {})
                r.raise_for_status()
            return True
        except Exception as e:
            logger.warning("[SPOTIFY-CONNECT] POST %s: %s", path, e)
            return False

    @staticmethod
    def _parse_status(st: dict | None) -> dict:
        """Statut go-librespot -> now-playing commun {playing, title, artist, ...}.

        Tolérant aux variations de schéma entre versions de go-librespot : on lit
        les champs avec des fallbacks, jamais d'accès dur.
        """
        if not isinstance(st, dict):
            return {"playing": False}
        track = st.get("track") or {}
        if not track:
            return {"playing": False}
        artists = track.get("artist_names") or track.get("artists") or []
        if isinstance(artists, str):
            artists = [artists]
        paused = bool(st.get("paused"))
        stopped = bool(st.get("stopped"))
        return {
            "playing": not stopped and not paused,
            "paused": paused,
            "title": track.get("name") or track.get("title") or "",
            "artist": ", ".join(a for a in artists if a),
            "album": track.get("album_name") or track.get("album") or "",
            "cover": track.get("album_cover_url") or track.get("cover") or None,
            "uri": track.get("uri") or "",
            "progress_ms": int(track.get("position") or track.get("position_ms") or 0),
            "duration_ms": int(track.get("duration") or track.get("duration_ms") or 0),
            "source": "spotify_connect",
        }

    # ------------------------------------------------------------------ cycle de vie
    @property
    def status(self) -> str:
        # 'ok' si l'API go-librespot a répondu au moins une fois ; sinon
        # 'not_connected' (binaire pas lancé / injoignable).
        return "ok" if self._reachable else "not_connected"

    async def start(self) -> None:
        st = await self._get("/status")
        self._reachable = st is not None
        if self._reachable:
            who = (st or {}).get("username") or "(non connecté)"
            logger.info("[SPOTIFY-CONNECT] go-librespot joignable sur %s (compte %s)", self._base, who)
        else:
            logger.warning(
                "[SPOTIFY-CONNECT] go-librespot injoignable sur %s — lance le binaire "
                "(API activée) puis sélectionne « PiBoard » dans l'app Spotify", self._base)

    # ------------------------------------------------------------------ recherche / lecture (récepteur)
    async def search_tracks(self, query: str, limit: int = 10) -> list[dict]:
        # go-librespot ne fait pas de recherche : on pilote depuis l'app Spotify.
        return []

    async def search_and_play(self, query: str) -> dict:
        return {"playing": False, "error": _RECEIVER_HINT}

    async def play_uri(self, uri: str) -> dict:
        return {"playing": False, "error": _RECEIVER_HINT}

    async def play_tracks(self, items: list[str]) -> dict:
        return {"playing": False, "error": _RECEIVER_HINT}

    # ------------------------------------------------------------------ playlists
    async def get_playlists(self) -> list[dict]:
        return []

    async def play_playlist(self, uri: str) -> dict:
        return {"playing": False, "error": _RECEIVER_HINT}

    # ------------------------------------------------------------------ file / transport
    async def get_queue(self) -> list[dict]:
        # go-librespot n'expose pas la file complète ; le « suivant » la fait avancer.
        return []

    async def get_current(self) -> dict:
        st = await self._get("/status")
        self._reachable = st is not None
        return self._parse_status(st)

    async def pause(self) -> dict:
        ok = await self._post("/player/pause")
        return {"paused": ok}

    async def resume(self) -> dict:
        ok = await self._post("/player/resume")
        return {"resumed": ok}

    async def next_track(self) -> dict:
        ok = await self._post("/player/next")
        cur = await self.get_current()
        cur["skipped"] = ok
        return cur

    async def previous_track(self) -> dict:
        ok = await self._post("/player/prev")
        return {"skipped": ok}

    async def seek(self, position_ms: int) -> dict:
        ok = await self._post("/player/seek", {"position": max(0, int(position_ms))})
        return {"seeked": ok}
