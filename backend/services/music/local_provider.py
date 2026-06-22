"""Fournisseur musical BIBLIOTHÈQUE LOCALE — 100 % hors-ligne et légal.

Indexe les fichiers audio d'un dossier (`MUSIC_LIBRARY_DIR`, défaut ~/Music) et
les joue via le lecteur mpv partagé (PipeWire -> AirPlay -> enceintes). Lit les
tags (titre/artiste/album/durée) avec **mutagen** si présent, sinon retombe sur
le nom de fichier / dossier parent. Aucune dépendance dure : sans mutagen ça
marche quand même.

Implémente l'interface commune `MusicProvider` (base.py). Tout est async ; le
scan disque (potentiellement lent) tourne dans un executor pour ne jamais geler
la boucle. URI = `local:<chemin relatif au dossier>` ; on refuse tout chemin qui
sortirait de la bibliothèque (anti path-traversal).
"""
from __future__ import annotations

import asyncio
import logging
import os
import random

from .base import MusicProvider

try:
    from .player import MusicPlayer
except Exception:  # pragma: no cover
    MusicPlayer = None  # type: ignore

try:
    import mutagen  # tags optionnels
    _HAS_MUTAGEN = True
except Exception:
    _HAS_MUTAGEN = False

logger = logging.getLogger(__name__)

_AUDIO_EXT = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".wma", ".aiff"}
_URI_PREFIX = "local:"
_MAX_FILES = 20000  # garde-fou : on n'indexe pas au-delà (bibliothèques géantes)


class LocalProvider(MusicProvider):
    """Bibliothèque de fichiers locale -> mpv. 100 % hors-ligne."""

    def __init__(self) -> None:
        super().__init__()
        from config import MUSIC_LIBRARY_DIR
        self._root = os.path.abspath(os.path.expanduser(MUSIC_LIBRARY_DIR))
        self._player = MusicPlayer(on_track_change=self._on_track_change) if MusicPlayer else None
        self._index: list[dict] = []  # [{path, title, artist, album, uri, duration_ms}]

    # ------------------------------------------------------------------ scan / index

    def _read_tags(self, path: str) -> dict:
        """Tags d'un fichier (mutagen si dispo, sinon nom de fichier/dossier)."""
        rel = os.path.relpath(path, self._root)
        title = os.path.splitext(os.path.basename(path))[0]
        artist = ""
        album = os.path.basename(os.path.dirname(path))
        duration_ms = 0
        if _HAS_MUTAGEN:
            try:
                mf = mutagen.File(path, easy=True)
                if mf is not None:
                    title = (mf.get("title", [title]) or [title])[0]
                    artist = (mf.get("artist", [""]) or [""])[0]
                    album = (mf.get("album", [album]) or [album])[0]
                    if mf.info and getattr(mf.info, "length", 0):
                        duration_ms = int(mf.info.length * 1000)
            except Exception:
                pass
        return {
            "path": path,
            "title": title or os.path.basename(path),
            "artist": artist,
            "album": album,
            "uri": _URI_PREFIX + rel,
            "duration_ms": duration_ms,
        }

    def _scan(self) -> list[dict]:
        """Parcourt la bibliothèque (bloquant -> à lancer en executor)."""
        out: list[dict] = []
        if not os.path.isdir(self._root):
            return out
        for dirpath, _dirs, files in os.walk(self._root):
            for f in files:
                if os.path.splitext(f)[1].lower() in _AUDIO_EXT:
                    out.append(self._read_tags(os.path.join(dirpath, f)))
                    if len(out) >= _MAX_FILES:
                        logger.warning("[LOCAL] %d fichiers atteint -> index tronqué", _MAX_FILES)
                        return out
        return out

    def _to_item(self, entry: dict) -> dict:
        """Entrée d'index -> item LECTURE mpv (l'URL = le chemin du fichier)."""
        return {
            "url": entry["path"],
            "title": entry["title"],
            "artist": entry["artist"],
            "album": entry["album"],
            "cover": None,
            "uri": entry["uri"],
            "duration_ms": entry.get("duration_ms", 0),
        }

    def _resolve_uri(self, uri: str) -> dict | None:
        """`local:<rel>` -> entrée d'index, en refusant tout chemin hors-bibliothèque."""
        rel = uri[len(_URI_PREFIX):] if uri.startswith(_URI_PREFIX) else uri
        target = os.path.abspath(os.path.join(self._root, rel))
        if os.path.commonpath([target, self._root]) != self._root:
            logger.warning("[LOCAL] chemin hors bibliothèque refusé: %s", rel)
            return None
        return next((e for e in self._index if e["path"] == target), None)

    # ------------------------------------------------------------------ cycle de vie

    @property
    def status(self) -> str:
        if not os.path.isdir(self._root):
            return "no_credentials"  # dossier absent -> à configurer (UI: 'à configurer')
        return "ok"

    async def start(self) -> None:
        if not os.path.isdir(self._root):
            logger.warning("[LOCAL] dossier introuvable: %s (définis MUSIC_LIBRARY_DIR)", self._root)
            return
        loop = asyncio.get_event_loop()
        self._index = await loop.run_in_executor(None, self._scan)
        logger.info("[LOCAL] %d morceaux indexés depuis %s", len(self._index), self._root)

    async def _on_track_change(self, meta: dict) -> None:
        await self._broadcast({"type": "music", "data": {
            "playing": True,
            "title": meta.get("title", ""),
            "artist": meta.get("artist", ""),
            "album": meta.get("album", ""),
            "cover": meta.get("cover"),
            "uri": meta.get("uri", ""),
            "progress_ms": 0,
            "duration_ms": meta.get("duration_ms", 0),
        }})

    # ------------------------------------------------------------------ recherche / lecture

    def _match(self, query: str) -> list[dict]:
        q = query.lower().strip()
        if not q:
            return list(self._index)
        return [e for e in self._index
                if q in e["title"].lower() or q in e["artist"].lower() or q in e["album"].lower()]

    async def search_tracks(self, query: str, limit: int = 10) -> list[dict]:
        hits = self._match(query)[:limit]
        return [{"title": e["title"], "artist": e["artist"], "album": e["album"],
                 "cover": None, "uri": e["uri"]} for e in hits]

    async def search_and_play(self, query: str) -> dict:
        if not self._player:
            return {"playing": False, "error": "lecteur indisponible"}
        hits = self._match(query)
        if not hits:
            return {"playing": False, "error": "aucun morceau trouvé"}
        # La requête vide / sans correspondance forte = on mélange la sélection.
        if not query.strip():
            random.shuffle(hits)
        await self._player.play([self._to_item(e) for e in hits[:100]])
        logger.info("[LOCAL] lecture '%s' (%d morceaux)", query or "tout", min(len(hits), 100))
        return self._player.current()

    async def play_uri(self, uri: str) -> dict:
        if not self._player:
            return {"playing": False, "error": "lecteur indisponible"}
        entry = self._resolve_uri(uri)
        if not entry:
            return {"playing": False, "error": "morceau introuvable"}
        # Joue le morceau puis enchaîne sur le reste de son album (file naturelle).
        album_tracks = [e for e in self._index if e["album"] == entry["album"]]
        ordered = [entry] + [e for e in album_tracks if e["path"] != entry["path"]]
        await self._player.play([self._to_item(e) for e in ordered])
        return self._player.current()

    async def play_tracks(self, items: list[str]) -> dict:
        if not self._player:
            return {"playing": False, "error": "lecteur indisponible"}
        resolved: list[dict] = []
        for entry in items:
            e = self._resolve_uri(entry) if entry.startswith(_URI_PREFIX) else None
            if e is None:
                hits = self._match(entry)
                e = hits[0] if hits else None
            if e:
                resolved.append(self._to_item(e))
        if not resolved:
            return {"playing": False, "error": "aucun morceau"}
        await self._player.play(resolved)
        return self._player.current()

    # ------------------------------------------------------------------ playlists = dossiers

    async def get_playlists(self) -> list[dict]:
        """Chaque dossier de 1er niveau contenant de la musique = une 'playlist'."""
        albums: dict[str, int] = {}
        for e in self._index:
            albums[e["album"]] = albums.get(e["album"], 0) + 1
        return [{"name": name, "id": name, "uri": _URI_PREFIX + "album:" + name,
                 "cover": None, "tracks": n}
                for name, n in sorted(albums.items()) if name][:200]

    async def play_playlist(self, uri: str) -> dict:
        if not self._player:
            return {"playing": False, "error": "lecteur indisponible"}
        album = uri.split("album:")[-1]
        tracks = [e for e in self._index if e["album"] == album]
        if not tracks:
            return {"playing": False, "error": "album vide"}
        random.shuffle(tracks)
        await self._player.play([self._to_item(e) for e in tracks])
        logger.info("[LOCAL] album '%s' (%d morceaux)", album, len(tracks))
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

    async def seek(self, position_ms: int) -> dict:
        if not self._player:
            return {"seeked": False}
        ok = await self._player.seek(int(position_ms) // 1000)
        return {"seeked": bool(ok)}

    async def get_current(self) -> dict:
        return await self._player.current_live() if self._player else {"playing": False}
