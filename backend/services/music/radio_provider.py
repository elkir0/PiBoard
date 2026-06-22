"""Fournisseur musical RADIO INTERNET — 100 % légal, sans compte, sans clé.

Source : l'annuaire communautaire **radio-browser.info** (API publique gratuite,
des dizaines de milliers de stations). On résout une URL de flux puis on la
pousse au lecteur mpv partagé (PipeWire -> AirPlay -> enceintes), exactement
comme les autres providers. C'est le DÉFAUT universel : il marche dès
l'installation, sans aucun identifiant.

Implémente l'interface commune `MusicProvider` (voir base.py). Tout est async ;
aucune méthode ne lève — en cas d'échec on logge `[RADIO] ...` et on renvoie un
dict dégradé. La radio est un flux LIVE : pas de file/seek/durée au sens piste ;
on expose une petite liste de stations « voisines » comme file pour que
suivant/précédent zappent de station.

Étiquette radio-browser : User-Agent identifiant + enregistrement du « clic » de
lecture (best-effort, aide leurs statistiques). Plusieurs miroirs avec bascule.
"""
from __future__ import annotations

import asyncio
import logging
import random

import httpx

from .base import MusicProvider

try:
    from .player import MusicPlayer
except Exception:  # pragma: no cover
    MusicPlayer = None  # type: ignore

logger = logging.getLogger(__name__)

# Miroirs radio-browser connus (round-robin DNS sur all.api…). On tente dans
# l'ordre et on mémorise celui qui répond. Voir https://api.radio-browser.info/
_MIRRORS = [
    "https://de1.api.radio-browser.info",
    "https://de2.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
    "https://all.api.radio-browser.info",
]
_UA = "PiBoard/1.0 (+https://github.com/elkir0/Pi4-Board)"
_URI_PREFIX = "radio:"
# Listes « playlists » virtuelles exposées dans l'UI.
_VIRTUAL_PLAYLISTS = [
    {"id": "topvote", "name": "Radios populaires", "endpoint": "/json/stations/topvote/40"},
    {"id": "topclick", "name": "Plus écoutées", "endpoint": "/json/stations/topclick/40"},
]


class RadioProvider(MusicProvider):
    """Radio internet via radio-browser.info -> mpv. Aucun compte requis."""

    def __init__(self) -> None:
        super().__init__()
        self._player = MusicPlayer(on_track_change=self._on_track_change) if MusicPlayer else None
        self._base: str | None = None  # miroir radio-browser actif

    # ------------------------------------------------------------------ HTTP

    async def _api(self, path: str, params: dict | None = None) -> list | dict | None:
        """GET sur le miroir actif (avec bascule). Renvoie le JSON ou None."""
        mirrors = ([self._base] if self._base else []) + [m for m in _MIRRORS if m != self._base]
        for base in mirrors:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(8), headers={"User-Agent": _UA}) as c:
                    r = await c.get(base + path, params=params or {})
                    r.raise_for_status()
                    self._base = base  # ce miroir marche -> on le garde
                    return r.json()
            except Exception as e:
                logger.debug("[RADIO] miroir %s KO: %s", base, e)
                continue
        logger.warning("[RADIO] aucun miroir radio-browser joignable")
        return None

    async def _register_click(self, uuid: str) -> None:
        """Étiquette radio-browser : signale une écoute (best-effort, non bloquant)."""
        if not uuid:
            return
        try:
            await self._api(f"/json/url/{uuid}")
        except Exception:
            pass

    @staticmethod
    def _station_to_track(s: dict) -> dict:
        """Station radio-browser -> item commun {title, artist, album, cover, uri}."""
        tags = (s.get("tags") or "").split(",")
        sub = ", ".join(t.strip() for t in tags[:2] if t.strip()) or (s.get("country") or "Radio")
        codec = (s.get("codec") or "").upper()
        bitrate = s.get("bitrate") or 0
        return {
            "title": s.get("name", "Radio").strip(),
            "artist": sub,
            "album": (f"{codec} {bitrate}k" if codec else "Radio en direct"),
            "cover": s.get("favicon") or None,
            "uri": _URI_PREFIX + (s.get("stationuuid") or ""),
        }

    def _station_to_item(self, s: dict) -> dict | None:
        """Item LECTURE pour mpv : ajoute l'URL de flux résolue. None si injouable."""
        url = s.get("url_resolved") or s.get("url")
        if not url:
            return None
        track = self._station_to_track(s)
        track["url"] = url
        track["duration_ms"] = 0  # flux live
        return track

    # ------------------------------------------------------------------ cycle de vie

    @property
    def status(self) -> str:
        # Aucun compte : prêt dès qu'un miroir répond. On reste optimiste ('ok')
        # même avant le 1er appel ; les échecs réseau sont gérés par requête.
        return "ok"

    async def start(self) -> None:
        # Résout un miroir au démarrage (warm-up) pour que la 1re commande soit rapide.
        servers = await self._api("/json/stats")
        if self._base:
            logger.info("[RADIO] prêt (miroir %s)", self._base)
        else:
            logger.warning("[RADIO] démarré mais aucun miroir joignable pour l'instant")

    async def _on_track_change(self, meta: dict) -> None:
        """Push du now-playing quand mpv change de station (suivant/précédent)."""
        await self._broadcast({"type": "music", "data": {
            "playing": True,
            "title": meta.get("title", ""),
            "artist": meta.get("artist", ""),
            "album": meta.get("album", ""),
            "cover": meta.get("cover"),
            "uri": meta.get("uri", ""),
            "progress_ms": 0,
            "duration_ms": 0,
        }})

    # ------------------------------------------------------------------ recherche / lecture

    async def search_tracks(self, query: str, limit: int = 10) -> list[dict]:
        data = await self._api("/json/stations/search", {
            "name": query, "limit": limit, "hidebroken": "true",
            "order": "votes", "reverse": "true",
        })
        if not isinstance(data, list):
            return []
        return [self._station_to_track(s) for s in data]

    async def _resolve(self, query: str, limit: int = 12) -> list[dict]:
        """Cherche des stations jouables (URL résolue) pour une requête texte."""
        data = await self._api("/json/stations/search", {
            "name": query, "limit": limit, "hidebroken": "true",
            "order": "votes", "reverse": "true",
        })
        if not isinstance(data, list):
            return []
        return [it for it in (self._station_to_item(s) for s in data) if it]

    async def search_and_play(self, query: str) -> dict:
        if not self._player:
            return {"playing": False, "error": "lecteur indisponible"}
        items = await self._resolve(query)
        if not items:
            logger.info("[RADIO] aucune station pour '%s'", query)
            return {"playing": False, "error": "aucune station trouvée"}
        # La 1re station joue ; les voisines forment la file (suivant = zapping).
        await self._player.play(items)
        asyncio.create_task(self._register_click(items[0]["uri"][len(_URI_PREFIX):]))
        logger.info("[RADIO] lecture '%s' (%d stations en file)", items[0]["title"], len(items))
        return self._player.current()

    async def play_uri(self, uri: str) -> dict:
        if not self._player:
            return {"playing": False, "error": "lecteur indisponible"}
        uuid = uri[len(_URI_PREFIX):] if uri.startswith(_URI_PREFIX) else uri
        data = await self._api(f"/json/stations/byuuid/{uuid}")
        item = self._station_to_item(data[0]) if isinstance(data, list) and data else None
        if not item:
            return {"playing": False, "error": "station introuvable"}
        await self._player.play([item])
        asyncio.create_task(self._register_click(uuid))
        return self._player.current()

    async def play_tracks(self, items: list[str]) -> dict:
        """Joue une liste de requêtes/uris (sert l'AI mix). Chaque entrée ->
        meilleure station correspondante."""
        if not self._player:
            return {"playing": False, "error": "lecteur indisponible"}
        resolved: list[dict] = []
        for entry in items:
            if entry.startswith(_URI_PREFIX):
                d = await self._api(f"/json/stations/byuuid/{entry[len(_URI_PREFIX):]}")
                it = self._station_to_item(d[0]) if isinstance(d, list) and d else None
                if it:
                    resolved.append(it)
            else:
                found = await self._resolve(entry, limit=1)
                if found:
                    resolved.append(found[0])
        if not resolved:
            return {"playing": False, "error": "aucune station"}
        await self._player.play(resolved)
        return self._player.current()

    # ------------------------------------------------------------------ playlists (virtuelles)

    async def get_playlists(self) -> list[dict]:
        out = []
        for pl in _VIRTUAL_PLAYLISTS:
            out.append({
                "name": pl["name"], "id": pl["id"], "uri": _URI_PREFIX + "list:" + pl["id"],
                "cover": None, "tracks": 0,
            })
        return out

    async def play_playlist(self, uri: str) -> dict:
        if not self._player:
            return {"playing": False, "error": "lecteur indisponible"}
        pid = uri.split("list:")[-1]
        pl = next((p for p in _VIRTUAL_PLAYLISTS if p["id"] == pid), None)
        if not pl:
            return {"playing": False, "error": "liste inconnue"}
        data = await self._api(pl["endpoint"])
        items = [it for it in (self._station_to_item(s) for s in (data or [])) if it]
        if not items:
            return {"playing": False, "error": "liste vide"}
        random.shuffle(items)
        await self._player.play(items)
        logger.info("[RADIO] liste '%s' (%d stations)", pl["name"], len(items))
        return self._player.current()

    # ------------------------------------------------------------------ file / transport

    async def get_queue(self) -> list[dict]:
        return self._player.upcoming() if self._player else []

    async def pause(self) -> dict:
        return await self._player.pause() if self._player else {"paused": False}

    async def resume(self) -> dict:
        return await self._player.resume() if self._player else {"resumed": False}

    async def next_track(self) -> dict:
        if not self._player:
            return {"playing": False}
        cur = await self._player.next()
        cur["skipped"] = True
        return cur

    async def previous_track(self) -> dict:
        if not self._player:
            return {"skipped": False}
        await self._player.prev()
        return {"skipped": True}

    async def get_current(self) -> dict:
        return await self._player.current_live() if self._player else {"playing": False}

    # La radio est un flux live : le seek n'a pas de sens mais ne doit pas casser.
    async def seek(self, position_ms: int) -> dict:
        return {"seeked": False}
