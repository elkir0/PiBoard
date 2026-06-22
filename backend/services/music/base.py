"""Interface commune aux fournisseurs de musique (Spotify, Deezer).

`main.py` parle a un objet `music` via ce contrat ; le frontend recoit des
messages generiques et ignore le provider actif. Tout est async ; aucune
methode ne doit lever — en cas d'echec, renvoyer un dict d'erreur degrade
(`{"playing": False, "error": ...}`) et logger, jamais crasher le main loop.

Formats de retour (communs aux providers) :
  - piste / now-playing : {playing, title, artist, album, cover, uri,
                           progress_ms, duration_ms}
  - resultat recherche  : {title, artist, album, cover, uri}
  - playlist            : {name, id, uri, cover, tracks}
  - item de file        : {title, artist, cover}

`uri` est opaque pour le frontend (Spotify: "spotify:track:..", Deezer:
"deezer:track:<id>"). Le provider sait la decoder.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable

logger = logging.getLogger(__name__)


class MusicProvider(ABC):
    """Contrat commun a tous les providers musicaux."""

    def __init__(self) -> None:
        self._broadcast_fn: Callable | None = None

    def set_broadcast(self, fn: Callable) -> None:
        """Enregistre la fonction de broadcast (push d'etat vers le frontend)."""
        self._broadcast_fn = fn

    async def _broadcast(self, message: dict) -> None:
        if self._broadcast_fn:
            try:
                await self._broadcast_fn(message)
            except Exception:
                pass

    # --- Etat / cycle de vie ---

    @property
    @abstractmethod
    def status(self) -> str:
        """'ok' | 'auth_required' | 'no_credentials' | 'not_connected'."""

    @abstractmethod
    async def start(self) -> None:
        """Initialise le provider (auth, decouverte device...). Ne crashe pas."""

    # --- Recherche / lecture ---

    @abstractmethod
    async def search_tracks(self, query: str, limit: int = 10) -> list[dict]:
        """Recherche texte -> liste {title, artist, album, cover, uri}."""

    @abstractmethod
    async def search_and_play(self, query: str) -> dict:
        """Cherche la meilleure piste, la joue et construit une file 'radio'."""

    @abstractmethod
    async def play_uri(self, uri: str) -> dict:
        """Joue une piste precise (+ file radio depuis son artiste)."""

    @abstractmethod
    async def play_tracks(self, items: list[str]) -> dict:
        """Joue une liste (requetes texte OU uris) — sert l'AI mix.

        Remplace l'ancien acces direct a `music._sp` dans handle_ai_mix.
        Retourne le now-playing de la 1re piste lancee.
        """

    # --- Playlists ---

    @abstractmethod
    async def get_playlists(self) -> list[dict]:
        """Playlists de l'utilisateur -> {name, id, uri, cover, tracks}."""

    @abstractmethod
    async def play_playlist(self, uri: str) -> dict:
        """Joue une playlist (en shuffle)."""

    # --- File / transport ---

    @abstractmethod
    async def get_queue(self) -> list[dict]:
        """File a venir -> liste {title, artist, cover}."""

    @abstractmethod
    async def pause(self) -> dict:
        """{paused: bool}."""

    @abstractmethod
    async def resume(self) -> dict:
        """{resumed: bool}."""

    @abstractmethod
    async def next_track(self) -> dict:
        """Passe au suivant -> now-playing (+ {skipped: True})."""

    @abstractmethod
    async def previous_track(self) -> dict:
        """Revient au precedent -> {skipped: bool}."""

    @abstractmethod
    async def get_current(self) -> dict:
        """Now-playing courant (ou {playing: False})."""
