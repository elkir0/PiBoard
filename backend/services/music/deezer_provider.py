"""Fournisseur Deezer (recherche, radio, playlists, Flow) derriere MusicProvider.

Deezer n'a pas de "Connect" comme Spotify : on lit le flux audio nous-memes.
DeezerProvider construit des items {url, meta} pointant vers la route locale
GET /deezer/stream/{id} (servie par main.py, qui dechiffre via deezer_stream),
puis pilote MusicPlayer (mpv -> PipeWire -> AirPlay -> Devialet).

deezer-py est SYNCHRONE (requests) : tous les appels passent par
run_in_executor, comme spotify.py enveloppe spotipy. Aucune methode ne crashe :
en cas d'echec -> dict degrade + log [DEEZER].
"""
from __future__ import annotations

import asyncio
import logging
import random

from config import DEEZER_ARL, DEEZER_QUALITY

from .base import MusicProvider

logger = logging.getLogger(__name__)

# Modules freres ecrits en parallele — import defensif pour que ce fichier
# s'importe proprement meme si player.py / deezer_stream.py manquent encore.
try:
    from .player import MusicPlayer
except Exception:  # pragma: no cover
    MusicPlayer = None  # type: ignore
    logger.warning("[DEEZER] player.MusicPlayer indisponible")

try:
    from . import deezer_stream
except Exception:  # pragma: no cover
    deezer_stream = None  # type: ignore
    logger.warning("[DEEZER] deezer_stream indisponible")

# Taille de la file radio construite apres une graine
RADIO_QUEUE_SIZE = 35
# Cover par defaut pour les objets gw (cles UPPERCASE)
_GW_COVER_BASE = "https://e-cdns-images.dzcdn.net/images/cover/"
_GW_COVER_SUFFIX = "/250x250-000000-80-0-0.jpg"


class DeezerProvider(MusicProvider):
    """Provider musical Deezer (alternative a Spotify)."""

    # Intervalle de refresh proactif de la session ARL (calque sur le
    # token_watchdog Spotify, 45 min) pour garder self._connected a jour
    # sans jamais bloquer la boucle d'evenements.
    REFRESH_INTERVAL_S = 45 * 60

    def __init__(self) -> None:
        super().__init__()
        self._player = MusicPlayer(on_track_change=self._on_track_change) if MusicPlayer else None
        self._status_override: str | None = None
        # Etat de connexion ARL : NE PROVIENT QUE des chemins async (start /
        # ensure_login en executor + token_watchdog). status/_ready le lisent
        # sans jamais appeler get_client() de maniere synchrone sur la boucle.
        self._connected: bool = False
        # uid du compte, cache au login pour eviter un acces synchrone a
        # client.current_user dans get_playlists()/_play_flow().
        self._uid = None

    @property
    def _dz(self):
        """Client deezer-py logge, auto-cicatrisant (re-login si session perdue).

        ⚠️ get_client() est SYNCHRONE et peut declencher un login_via_arl()
        bloquant (requests sans timeout). Ne JAMAIS l'appeler directement sur
        la boucle d'evenements : on y accede uniquement dans _exec() (executor)
        ou via ensure_login()/start()/token_watchdog (executor + wait_for).
        """
        return deezer_stream.get_client() if deezer_stream else None

    # --- Etat / cycle de vie ---

    @property
    def status(self) -> str:
        # Lecture PUREMENT non bloquante : self._connected est tenu a jour par
        # start()/token_watchdog (executor). Aucun appel get_client() ici.
        if self._status_override:
            return self._status_override
        if not DEEZER_ARL:
            return "no_credentials"
        if not self._connected:
            return "not_connected"
        return "ok"

    async def start(self) -> None:
        """Connexion au client deezer-py partage (login via ARL). Ne crashe pas."""
        if not DEEZER_ARL:
            logger.info("[DEEZER] Mode mock (pas d'ARL)")
            self._connected = False
            await self._broadcast_status()
            return
        if deezer_stream is None:
            logger.warning("[DEEZER] deezer_stream absent — provider degrade")
            self._connected = False
            self._status_override = "not_connected"
            await self._broadcast_status()
            return
        await self._login(timeout=15)
        await self._broadcast_status()

    async def _login(self, timeout: float = 15) -> bool:
        """Login ARL borne (executor + wait_for) et mise a jour de l'etat.

        Met a jour self._connected / self._uid UNIQUEMENT depuis ce chemin async
        (jamais d'appel get_client synchrone sur la boucle). Retourne l'etat.
        """
        try:
            # Pre-chauffe le client partage (login ARL) dans l'executor, borne
            # par wait_for pour ne jamais geler la boucle si requests bloque.
            client = await asyncio.wait_for(deezer_stream.ensure_login(), timeout=timeout)
            if client:
                self._status_override = None
                user = getattr(client, "current_user", None) or {}
                self._uid = user.get("id") or self._uid
                self._connected = True
                logger.info("[DEEZER] Connecte (user=%s)", user.get("name", "?"))
            else:
                self._connected = False
                self._status_override = "auth_required"
                logger.warning("[DEEZER] Login ARL echoue — auth_required")
        except asyncio.TimeoutError:
            self._connected = False
            logger.warning("[DEEZER] Timeout login — mode degrade")
            self._status_override = "not_connected"
        except Exception as e:
            self._connected = False
            logger.error("[DEEZER] Erreur login: %s", e)
            self._status_override = "auth_required"
        return self._connected

    async def token_watchdog(self) -> None:
        """Rafraichit proactivement la session ARL (~45 min) — calque sur le
        token_watchdog Spotify. Maintient self._connected sans jamais bloquer la
        boucle : tout passe par _login() (executor + wait_for).

        Cable automatiquement par main.py via hasattr(music, "token_watchdog").
        """
        if not DEEZER_ARL or deezer_stream is None:
            return
        while True:
            await asyncio.sleep(self.REFRESH_INTERVAL_S)
            try:
                was = self._connected
                ok = await self._login(timeout=15)
                if ok and not was:
                    logger.info("[DEEZER] Watchdog: session ARL recuperee")
                elif ok:
                    logger.info("[DEEZER] Watchdog: session ARL OK")
                else:
                    logger.warning("[DEEZER] Watchdog: session ARL indisponible")
                # L'etat a pu changer (perte/recuperation) -> previens le front.
                if self._connected != was:
                    await self._broadcast_status()
            except Exception as e:
                # Zero-crash : le watchdog ne doit jamais tuer la boucle.
                logger.warning("[DEEZER] Watchdog erreur ignoree: %s", e)

    async def _broadcast_status(self) -> None:
        # Canal generique attendu par le frontend (idem Spotify).
        await self._broadcast({"type": "spotify_status", "data": self.status})

    async def _on_track_change(self, meta: dict) -> None:
        """Callback MusicPlayer quand la piste avance — push le now-playing.

        Diffuse sur le canal 'music' (celui que le frontend ecoute). Awaitable :
        le poll loop du player l'attend, donc pas de task fire-and-forget perdue.
        """
        await self._broadcast({"type": "music", "data": {**meta, "playing": True}})

    # --- Helpers ---

    def _ready(self) -> bool:
        # Non bloquant : on s'appuie sur l'etat tenu par start()/token_watchdog,
        # plus aucun acces get_client() synchrone ici.
        return self._connected and self._player is not None

    async def _exec(self, fn):
        """Lance un appel deezer-py bloquant dans l'executor.

        C'est le SEUL endroit (avec _login) ou le client deezer-py est touche.
        get_client() (appele dans fn via self._dz) peut re-loger si la session a
        saute : on l'execute donc toujours dans l'executor, jamais sur la boucle.
        En cas d'echec on remet self._connected=False (auto-cicatrisation : le
        prochain start()/watchdog re-tentera le login).
        """
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, fn)
        except Exception:
            # Perte de session probable -> degrade l'etat affiche; le watchdog
            # ou un nouveau start() re-loggera. On re-leve pour que l'appelant
            # garde son fallback existant ({"error": ...}, [], etc.).
            self._connected = False
            raise

    async def _user_id(self):
        """uid du compte Deezer, sans acces synchrone a current_user.

        Renvoie l'uid cache au login si dispo ; sinon le lit dans l'executor
        (via _exec, get_client y est donc deja deporte) et le met en cache.
        """
        if self._uid:
            return self._uid
        try:
            uid = await self._exec(
                lambda: (getattr(self._dz, "current_user", None) or {}).get("id")
            )
        except Exception:
            return None
        if uid:
            self._uid = uid
        return uid

    def _stream_url(self, track_id) -> str:
        return f"http://127.0.0.1:8000/deezer/stream/{track_id}?fmt={DEEZER_QUALITY}"

    def _item_from_api(self, t: dict) -> dict:
        """Construit un item player depuis un objet API public (cles lowercase)."""
        tid = t.get("id")
        album = t.get("album") or {}
        artist = t.get("artist") or {}
        cover = album.get("cover_medium") or album.get("cover_big") or album.get("cover")
        return {
            "url": self._stream_url(tid),
            "title": t.get("title", ""),
            "artist": artist.get("name", ""),
            "album": album.get("title", ""),
            "cover": cover,
            "uri": f"deezer:track:{tid}",
            "duration_ms": int(t.get("duration", 0)) * 1000,
        }

    def _item_from_gw(self, t: dict) -> dict:
        """Construit un item player depuis un objet gw (cles UPPERCASE)."""
        tid = t.get("SNG_ID")
        pic = t.get("ALB_PICTURE", "")
        cover = f"{_GW_COVER_BASE}{pic}{_GW_COVER_SUFFIX}" if pic else None
        return {
            "url": self._stream_url(tid),
            "title": t.get("SNG_TITLE", ""),
            "artist": t.get("ART_NAME", ""),
            "album": t.get("ALB_TITLE", ""),
            "cover": cover,
            "uri": f"deezer:track:{tid}",
            "duration_ms": int(t.get("DURATION", 0) or 0) * 1000,
        }

    async def _radio_items(self, artist_id, exclude_id=None) -> list[dict]:
        """File radio (~35 pistes) a partir de l'artiste d'une graine."""
        if not artist_id:
            return []
        items: list[dict] = []
        try:
            radio = await self._exec(
                lambda: self._dz.api.get_artist_radio(artist_id, limit=RADIO_QUEUE_SIZE).get("data", [])
            )
            for t in radio:
                if exclude_id and str(t.get("id")) == str(exclude_id):
                    continue
                items.append(self._item_from_api(t))
        except Exception as e:
            logger.warning("[DEEZER] Radio echouee, fallback top: %s", e)
        if not items:
            try:
                top = await self._exec(
                    lambda: self._dz.api.get_artist_top(artist_id, limit=RADIO_QUEUE_SIZE).get("data", [])
                )
                for t in top:
                    if exclude_id and str(t.get("id")) == str(exclude_id):
                        continue
                    items.append(self._item_from_api(t))
            except Exception as e:
                logger.warning("[DEEZER] Top artiste echoue: %s", e)
        return items[:RADIO_QUEUE_SIZE]

    async def _resolve_track(self, ref: str) -> dict | None:
        """Resout une requete texte OU 'deezer:track:<id>' -> objet API (lowercase)."""
        try:
            if ref.startswith("deezer:track:"):
                tid = ref.split(":")[-1]
                return await self._exec(lambda: self._dz.api.get_track(tid))
            data = await self._exec(
                lambda: self._dz.api.search_track(ref).get("data", [])
            )
            return data[0] if data else None
        except Exception as e:
            logger.warning("[DEEZER] Resolution echouee pour '%s': %s", ref, e)
            return None

    # --- Recherche / lecture ---

    async def search_tracks(self, query: str, limit: int = 10) -> list[dict]:
        if not self._ready():
            return []
        try:
            data = await self._exec(
                lambda: self._dz.api.search_track(query).get("data", [])
            )
            out = []
            for t in data[:limit]:
                album = t.get("album") or {}
                artist = t.get("artist") or {}
                out.append({
                    "title": t.get("title", ""),
                    "artist": artist.get("name", ""),
                    "album": album.get("title", ""),
                    "cover": album.get("cover_medium") or album.get("cover_big"),
                    "uri": f"deezer:track:{t.get('id')}",
                })
            return out
        except Exception as e:
            logger.error("[DEEZER] Erreur search: %s", e)
            return []

    async def search_and_play(self, query: str) -> dict:
        if not self._ready():
            return {"error": "Deezer non configure", "playing": False}
        try:
            # Requete vide -> Flow personnalise ("mets de la musique")
            if not query or not query.strip():
                return await self._play_flow()

            data = await self._exec(
                lambda: self._dz.api.search_track(query).get("data", [])
            )
            if not data:
                return {"error": f"Aucun resultat pour '{query}'", "playing": False}

            seed = data[0]
            seed_item = self._item_from_api(seed)
            artist_id = (seed.get("artist") or {}).get("id")
            radio = await self._radio_items(artist_id, exclude_id=seed.get("id"))

            await self._player.play([seed_item] + radio)
            logger.info(
                "[DEEZER] Lecture: %s - %s (+%d radio)",
                seed_item["artist"], seed_item["title"], len(radio),
            )
            return {**self._now_playing(seed_item), "queue_size": len(radio)}
        except Exception as e:
            logger.error("[DEEZER] Erreur search_and_play: %s", e)
            return {"error": str(e), "playing": False}

    async def _play_flow(self) -> dict:
        """Joue le Flow personnalise Deezer (pas de graine fournie)."""
        try:
            uid = await self._user_id()
            if not uid:
                return {"error": "Flow indisponible", "playing": False}
            data = await self._exec(
                lambda: self._dz.api.get_user_flow(uid, limit=RADIO_QUEUE_SIZE).get("data", [])
            )
            if not data:
                return {"error": "Flow Deezer vide", "playing": False}
            items = [self._item_from_api(t) for t in data[:RADIO_QUEUE_SIZE]]
            await self._player.play(items)
            logger.info("[DEEZER] Flow lance (%d pistes)", len(items))
            return {**self._now_playing(items[0]), "queue_size": len(items) - 1}
        except Exception as e:
            logger.error("[DEEZER] Erreur Flow: %s", e)
            return {"error": str(e), "playing": False}

    async def play_uri(self, uri: str) -> dict:
        if not self._ready():
            return {"playing": False}
        try:
            if uri.startswith("deezer:playlist:"):
                return await self.play_playlist(uri)
            tid = uri.split(":")[-1]
            track = await self._exec(lambda: self._dz.api.get_track(tid))
            if not track:
                return {"playing": False, "error": "Piste introuvable"}
            seed_item = self._item_from_api(track)
            artist_id = (track.get("artist") or {}).get("id")
            radio = await self._radio_items(artist_id, exclude_id=track.get("id"))
            await self._player.play([seed_item] + radio)
            logger.info(
                "[DEEZER] play_uri: %s - %s (+%d radio)",
                seed_item["artist"], seed_item["title"], len(radio),
            )
            return {**self._now_playing(seed_item), "queue_size": len(radio)}
        except Exception as e:
            logger.error("[DEEZER] Erreur play_uri: %s", e)
            return {"playing": False, "error": str(e)}

    async def play_tracks(self, items: list[str]) -> dict:
        """Joue une liste de requetes/uris (AI mix) sans file radio ajoutee."""
        if not self._ready():
            return {"playing": False}
        try:
            resolved: list[dict] = []
            for ref in items:
                track = await self._resolve_track(ref)
                if track:
                    resolved.append(self._item_from_api(track))
            if not resolved:
                return {"error": "Aucune piste resolue", "playing": False}
            await self._player.play(resolved)
            logger.info("[DEEZER] AI mix: %d pistes", len(resolved))
            return {**self._now_playing(resolved[0]), "queue_size": len(resolved) - 1}
        except Exception as e:
            logger.error("[DEEZER] Erreur play_tracks: %s", e)
            return {"playing": False, "error": str(e)}

    # --- Playlists ---

    async def get_playlists(self) -> list[dict]:
        if not self._ready():
            return []
        try:
            uid = await self._user_id()
            if not uid:
                return []
            res = await self._exec(lambda: self._dz.gw.get_user_playlists(uid))
            rows = res if isinstance(res, list) else res.get("data", [])
            out = []
            for p in rows:
                # get_user_playlists renvoie des objets style API publique
                # (cles lowercase) ; on garde un fallback gw UPPERCASE par securite.
                pid = p.get("id") or p.get("PLAYLIST_ID")
                if not pid:
                    continue
                out.append({
                    "name": p.get("title") or p.get("TITLE", ""),
                    "id": pid,
                    "uri": f"deezer:playlist:{pid}",
                    "cover": p.get("picture_medium") or p.get("picture_big"),
                    "tracks": int(p.get("nb_tracks") or p.get("NB_SONG") or 0),
                })
            return out
        except Exception as e:
            logger.error("[DEEZER] Erreur playlists: %s", e)
            return []

    async def play_playlist(self, uri: str) -> dict:
        if not self._ready():
            return {"playing": False}
        try:
            pid = uri.split(":")[-1]
            res = await self._exec(lambda: self._dz.gw.get_playlist_tracks(pid))
            tracks = res if isinstance(res, list) else res.get("data", [])
            tracks = [t for t in tracks if t.get("SNG_ID")]  # ignore episodes/indispos
            if not tracks:
                return {"error": "Playlist vide", "playing": False}
            items = [self._item_from_gw(t) for t in tracks]
            random.shuffle(items)
            await self._player.play(items)
            logger.info("[DEEZER] Playlist %s lancee (%d pistes, shuffle)", pid, len(items))
            return {**self._now_playing(items[0]), "queue_size": len(items) - 1}
        except Exception as e:
            logger.error("[DEEZER] Erreur play_playlist: %s", e)
            return {"playing": False, "error": str(e)}

    # --- File / transport ---

    async def get_queue(self) -> list[dict]:
        if not self._player:
            return []
        try:
            return self._player.upcoming()
        except Exception as e:
            logger.error("[DEEZER] Erreur queue: %s", e)
            return []

    async def pause(self) -> dict:
        if not self._player:
            return {"paused": False}
        try:
            res = await self._player.pause()
            logger.info("[DEEZER] Pause")
            return {"paused": bool(res.get("paused", True))}
        except Exception as e:
            logger.error("[DEEZER] Erreur pause: %s", e)
            return {"paused": False, "error": str(e)}

    async def seek(self, position_ms: int) -> None:
        """Deplace la lecture a position_ms (depuis l'UI : barre de progression)."""
        if not self._player:
            return
        try:
            await self._player.seek(int(position_ms) // 1000)
        except Exception as e:
            logger.error("[DEEZER] Erreur seek: %s", e)

    async def resume(self) -> dict:
        if not self._player:
            return {"resumed": False}
        try:
            res = await self._player.resume()
            logger.info("[DEEZER] Resume")
            return {"resumed": bool(res.get("resumed", True))}
        except Exception as e:
            logger.error("[DEEZER] Erreur resume: %s", e)
            return {"resumed": False, "error": str(e)}

    async def stop(self) -> dict:
        """Arret franc : coupe mpv et vide la file (bouton Stop de l'UI)."""
        if not self._player:
            return {"playing": False}
        try:
            await self._player.stop()
            logger.info("[DEEZER] Stop")
        except Exception as e:
            logger.error("[DEEZER] Erreur stop: %s", e)
        return {"playing": False}

    async def next_track(self) -> dict:
        if not self._player:
            return {"skipped": False}
        try:
            current = await self._player.next()
            logger.info("[DEEZER] Suivant")
            return {**current, "skipped": True}
        except Exception as e:
            logger.error("[DEEZER] Erreur next: %s", e)
            return {"skipped": False, "error": str(e)}

    async def previous_track(self) -> dict:
        if not self._player:
            return {"skipped": False}
        try:
            current = await self._player.prev()
            logger.info("[DEEZER] Precedent")
            return {**current, "skipped": True}
        except Exception as e:
            logger.error("[DEEZER] Erreur previous: %s", e)
            return {"skipped": False, "error": str(e)}

    async def get_current(self) -> dict:
        if not self._player:
            return {"playing": False}
        try:
            # current_live() lit time-pos/duration via mpv -> barre de progression reelle
            return await self._player.current_live()
        except Exception as e:
            logger.error("[DEEZER] Erreur current: %s", e)
            return {"playing": False}

    # --- Util now-playing ---

    def _now_playing(self, item: dict) -> dict:
        """Convertit un item player en dict now-playing du contrat."""
        return {
            "playing": True,
            "title": item.get("title", ""),
            "artist": item.get("artist", ""),
            "album": item.get("album", ""),
            "cover": item.get("cover"),
            "uri": item.get("uri"),
            "progress_ms": 0,
            "duration_ms": item.get("duration_ms", 0),
        }
