"""Fournisseur Spotify derriere MusicProvider — adaptateur fin sur MusicController.

Tout le metier Spotify (OAuth, librespot, recherche, radio, playlists) vit deja
dans `services.spotify.MusicController`. Ce provider ne fait que l'envelopper pour
satisfaire le contrat MusicProvider et l'exposer via le meme objet `music` que
DeezerProvider. Le MusicController interne reste accessible (`self._mc`) pour les
bricoles Spotify-only que `main.py` pilote encore quand provider=spotify
(get_auth_url, handle_callback, token_watchdog, _poller_skip_until...).

Seule methode reellement ajoutee ici : `play_tracks` (AI mix), qui reprend la
logique de l'ancien handle_ai_mix. Aucune methode ne crashe — les erreurs sont
loggees [SPOTIFY] et renvoyees en dict degrade par le MusicController.
"""
from __future__ import annotations

import asyncio
import logging

from .base import MusicProvider
from ..spotify import MusicController

logger = logging.getLogger(__name__)


class SpotifyProvider(MusicProvider):
    """Provider musical Spotify (delegue tout a un MusicController)."""

    def __init__(self) -> None:
        super().__init__()
        # MusicController interne — expose pour les helpers Spotify-only depuis main.py.
        self._mc = MusicController()

    # --- Etat / cycle de vie ---

    @property
    def status(self) -> str:
        return self._mc.status

    def set_broadcast(self, fn) -> None:
        # Delegue : c'est le MusicController qui pousse 'spotify_status'.
        self._broadcast_fn = fn
        self._mc.set_broadcast(fn)

    async def start(self) -> None:
        await self._mc.start()

    # --- Recherche / lecture ---

    async def search_tracks(self, query: str, limit: int = 10) -> list[dict]:
        return await self._mc.search_tracks(query, limit)

    async def search_and_play(self, query: str) -> dict:
        return await self._mc.search_and_play(query)

    async def play_uri(self, uri: str) -> dict:
        return await self._mc.play_uri(uri)

    async def play_tracks(self, items: list[str]) -> dict:
        """Joue une liste de requetes texte (AI mix). Reprend l'ancien handle_ai_mix.

        Pour chaque requete : search top 1 -> uri. Puis _find_device() +
        start_playback(uris=...). Retourne le now-playing de la 1re piste.
        """
        mc = self._mc
        if not mc._sp:
            return {"playing": False}
        loop = asyncio.get_event_loop()
        uris: list[str] = []
        first_info: dict | None = None
        for item in items:
            try:
                results = await loop.run_in_executor(
                    None, lambda s=item: mc._sp.search(q=s, type="track", limit=1, market="FR")
                )
                tracks = results.get("tracks", {}).get("items", [])
                if tracks:
                    uris.append(tracks[0]["uri"])
                    if not first_info:
                        t = tracks[0]
                        first_info = {
                            "playing": True,
                            "title": t["name"],
                            "artist": ", ".join(a["name"] for a in t["artists"]),
                            "album": t["album"]["name"],
                            "cover": t["album"]["images"][0]["url"] if t["album"]["images"] else None,
                            "uri": t["uri"],
                            "progress_ms": 0,
                            "duration_ms": t.get("duration_ms", 0),
                        }
            except Exception:
                pass

        if not uris:
            logger.warning("[SPOTIFY] AI mix: aucun morceau trouve")
            return {"playing": False, "error": "Aucun morceau trouve"}

        try:
            await mc._find_device()
            await loop.run_in_executor(
                None, lambda: mc._sp.start_playback(device_id=mc._device_id, uris=uris)
            )
            logger.info("[SPOTIFY] AI mix lance: %d morceaux", len(uris))
            return {**(first_info or {}), "queue_size": len(uris) - 1}
        except Exception as e:
            logger.error("[SPOTIFY] Erreur AI mix: %s", e)
            return {"playing": False, "error": str(e)}

    # --- Playlists ---

    async def get_playlists(self) -> list[dict]:
        return await self._mc.get_playlists()

    async def play_playlist(self, uri: str) -> dict:
        return await self._mc.play_playlist(uri)

    # --- File / transport ---

    async def get_queue(self) -> list[dict]:
        return await self._mc.get_queue()

    async def pause(self) -> dict:
        return await self._mc.pause()

    async def resume(self) -> dict:
        return await self._mc.resume()

    async def next_track(self) -> dict:
        return await self._mc.next_track()

    async def previous_track(self) -> dict:
        return await self._mc.previous_track()

    async def get_current(self) -> dict:
        return await self._mc.get_current()
