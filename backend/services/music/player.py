"""Lecteur audio-only base sur mpv, provider-agnostic.

mpv tourne en permanence en mode idle (`--idle=yes --no-video`) et reste
pilote via son socket IPC JSON (`/tmp/mpv-music-socket`). On lui pousse des
URLs (loadfile/playlist-*) sans qu'il prenne le DRM ni la sortie video : il
cohabite donc avec flutter-pi/Chromium. La sortie audio passe par le sink
PipeWire par defaut (le RAOP Devialet est deja le defaut sur le Pi) -> AirPlay.

On garde une liste interne `_items` de metadonnees PARALLELE a la playlist mpv
pour que current()/upcoming() renvoient {title, artist, cover, ...}. La piste
courante et la progression sont lues via les proprietes mpv `playlist-pos`,
`time-pos` et `duration`. Un poll detecte l'avance de piste et appelle
`on_track_change(meta)`.

Tout est async ; aucune methode ne crashe le main loop — en cas d'echec on
logge `[MUSIC] ...` et on renvoie un dict/valeur degrade.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Callable

logger = logging.getLogger(__name__)

MPV_SOCKET = "/tmp/mpv-music-socket"
_POLL_INTERVAL = 1.0  # secondes entre deux lectures d'etat mpv


class MusicPlayer:
    """Lecteur mpv audio-only persistant, pilote en IPC JSON."""

    def __init__(self, on_track_change: Callable | None = None) -> None:
        self._on_track_change = on_track_change
        self._proc: asyncio.subprocess.Process | None = None
        self._items: list[dict] = []          # metadonnees parallele a la playlist mpv
        self._index: int = 0                   # position courante (miroir de playlist-pos)
        self._paused: bool = False
        self._lock = asyncio.Lock()            # serialise les acces au socket IPC
        self._poll_task: asyncio.Task | None = None
        self._req_id: int = 0
        self._settle_until: float = 0.0       # fenetre anti-fausse-notif apres play/stop

    # ------------------------------------------------------------------ mpv lifecycle

    async def _ensure_mpv(self) -> bool:
        """Demarre mpv idle si besoin. Renvoie True si le process est vivant."""
        if self._proc is not None and self._proc.returncode is None:
            return True

        # Socket residuel d'une instance morte
        try:
            if os.path.exists(MPV_SOCKET):
                os.unlink(MPV_SOCKET)
        except Exception:
            pass

        try:
            self._proc = await asyncio.create_subprocess_exec(
                "mpv",
                "--no-video",
                "--ao=pulse",
                "--no-terminal",
                "--idle=yes",
                "--force-window=no",
                "--volume=100",
                "--audio-buffer=1",
                f"--input-ipc-server={MPV_SOCKET}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error("[MUSIC] mpv non installe")
            self._proc = None
            return False
        except Exception as e:
            logger.error("[MUSIC] Echec lancement mpv: %s", e)
            self._proc = None
            return False

        # Attendre que le socket IPC soit pret
        for _ in range(50):
            if os.path.exists(MPV_SOCKET):
                break
            await asyncio.sleep(0.05)
        else:
            logger.error("[MUSIC] Socket IPC mpv jamais apparu — abandon")
            try:
                self._proc.kill()
                await asyncio.wait_for(self._proc.wait(), timeout=2)
            except Exception:
                pass
            self._proc = None
            return False

        logger.info("[MUSIC] mpv idle demarre (PID %s)", getattr(self._proc, "pid", "?"))
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop())
        return True

    async def _mpv_ipc(self, command: list, want_result: bool = False):
        """Envoie une commande au socket IPC mpv.

        Si `want_result`, lit la reponse JSON et renvoie le champ `data`
        (ex: get_property). Sinon renvoie True/False (fire-and-forget).
        Robuste : ne leve jamais.
        """
        if self._proc is None or self._proc.returncode is not None:
            return None if want_result else False
        async with self._lock:
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(MPV_SOCKET), timeout=2
                )
                self._req_id += 1
                req_id = self._req_id
                msg = json.dumps({"command": command, "request_id": req_id}) + "\n"
                writer.write(msg.encode())
                await writer.drain()

                if not want_result:
                    return True

                # Lire jusqu'a la reponse correspondant a notre request_id
                for _ in range(20):
                    line = await asyncio.wait_for(reader.readline(), timeout=2)
                    if not line:
                        break
                    try:
                        resp = json.loads(line.decode())
                    except Exception:
                        continue
                    if resp.get("request_id") == req_id:
                        if resp.get("error") == "success":
                            return resp.get("data")
                        return None
                return None
            except Exception:
                return None if want_result else False
            finally:
                if writer is not None:
                    try:
                        writer.close()
                    except Exception:
                        pass

    async def _get_property(self, name: str):
        """Lit une propriete mpv (time-pos, duration, playlist-pos...)."""
        return await self._mpv_ipc(["get_property", name], want_result=True)

    # ------------------------------------------------------------------ poll / track-change

    async def _poll_loop(self) -> None:
        """Surveille `playlist-pos` pour detecter l'avance de piste."""
        try:
            while self._proc is not None and self._proc.returncode is None:
                await asyncio.sleep(_POLL_INTERVAL)
                pos = await self._get_property("playlist-pos")
                if pos is None or pos < 0:
                    continue
                pos = int(pos)
                if pos == self._index:
                    continue
                if not (0 <= pos < len(self._items)):
                    continue  # pos hors-bornes (course loadfile/clear) -> on ignore
                if time.monotonic() < self._settle_until:
                    continue  # mpv converge encore apres play/stop -> pas de fausse notif
                self._index = pos
                meta = self._items[pos]
                logger.info(
                    "[MUSIC] Piste %d/%d: %s - %s",
                    pos + 1, len(self._items),
                    meta.get("artist", "?"), meta.get("title", "?"),
                )
                if self._on_track_change:
                    try:
                        res = self._on_track_change(self._now_playing_meta(meta))
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        logger.warning("[MUSIC] on_track_change: %s", e)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("[MUSIC] Poll loop arrete: %s", e)

    # ------------------------------------------------------------------ helpers meta

    @staticmethod
    def _now_playing_meta(meta: dict) -> dict:
        """Vue 'now-playing' enrichie a partir d'une meta d'item."""
        return {
            "title": meta.get("title", ""),
            "artist": meta.get("artist", ""),
            "album": meta.get("album", ""),
            "cover": meta.get("cover"),
            "uri": meta.get("uri", ""),
            "duration_ms": meta.get("duration_ms", 0),
        }

    # ------------------------------------------------------------------ transport public

    async def play(self, items: list[dict]) -> None:
        """Remplace la file et lance la lecture depuis le 1er item."""
        if not await self._ensure_mpv():
            return
        if not items:
            await self.stop()
            return
        # Verrouille la SORTIE CHOISIE comme defaut AVANT de jouer (mpv --ao=pulse
        # suit le defaut) : la musique part toujours sur la sortie configuree,
        # quel que soit le point d'entree (voix ou UI).
        try:
            from audio.output import ensure_selected_output
            await ensure_selected_output()
        except Exception:
            pass
        try:
            self._items = list(items)
            self._index = 0
            self._paused = False
            self._settle_until = time.monotonic() + 2.0
            # 1er item: remplace toute la playlist et joue
            await self._mpv_ipc(["loadfile", items[0]["url"], "replace"])
            await self._mpv_ipc(["set_property", "pause", False])
            # Items suivants: ajoutes a la file
            for it in items[1:]:
                await self._mpv_ipc(["loadfile", it["url"], "append"])
            first = items[0]
            logger.info(
                "[MUSIC] Lecture %d piste(s): %s - %s",
                len(items), first.get("artist", "?"), first.get("title", "?"),
            )
            if self._on_track_change:
                try:
                    res = self._on_track_change(self._now_playing_meta(first))
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass
        except Exception as e:
            logger.error("[MUSIC] Erreur play: %s", e)

    async def append(self, items: list[dict]) -> None:
        """Ajoute des items en fin de file (mode append mpv)."""
        if not items:
            return
        if not await self._ensure_mpv():
            return
        try:
            for it in items:
                await self._mpv_ipc(["loadfile", it["url"], "append"])
                self._items.append(it)
            logger.info("[MUSIC] +%d piste(s) en file", len(items))
        except Exception as e:
            logger.error("[MUSIC] Erreur append: %s", e)

    async def pause(self) -> dict:
        await self._mpv_ipc(["set_property", "pause", True])
        self._paused = True
        return {"paused": True}

    async def resume(self) -> dict:
        if not await self._ensure_mpv():
            return {"resumed": False}
        await self._mpv_ipc(["set_property", "pause", False])
        self._paused = False
        return {"resumed": True}

    async def next(self) -> dict:
        """Passe a la piste suivante -> now-playing."""
        try:
            await self._mpv_ipc(["playlist-next", "weak"])
            await asyncio.sleep(0.15)
            # Resync _index sur la position reelle mpv (le poll loop ne le met a
            # jour que toutes les 1.0s -> sinon current() renvoie l'ancienne piste).
            pos = await self._get_property("playlist-pos")
            if pos is not None and 0 <= int(pos) < len(self._items):
                self._index = int(pos)
        except Exception as e:
            logger.warning("[MUSIC] next: %s", e)
        return self.current()

    async def prev(self) -> dict:
        """Revient a la piste precedente -> now-playing."""
        try:
            await self._mpv_ipc(["playlist-prev", "weak"])
            await asyncio.sleep(0.15)
            # Resync _index sur la position reelle mpv (idem next()).
            pos = await self._get_property("playlist-pos")
            if pos is not None and 0 <= int(pos) < len(self._items):
                self._index = int(pos)
        except Exception as e:
            logger.warning("[MUSIC] prev: %s", e)
        return self.current()

    async def seek(self, position_s: int) -> bool:
        """Va a une position ABSOLUE en secondes (timestamp depuis le debut)."""
        ok = await self._mpv_ipc(["seek", str(position_s), "absolute"])
        return bool(ok)

    async def stop(self) -> None:
        """Arrete la lecture et vide la file (mpv reste idle)."""
        try:
            await self._mpv_ipc(["stop"])
            await self._mpv_ipc(["playlist-clear"])
        except Exception:
            pass
        self._items = []
        self._index = 0
        self._paused = False
        self._settle_until = time.monotonic() + 2.0
        logger.info("[MUSIC] Stop (file videe)")

    # ------------------------------------------------------------------ etat / lecture

    def current(self) -> dict:
        """Now-playing courant (lecture best-effort des proprietes mpv)."""
        if not self._items or not (0 <= self._index < len(self._items)):
            return {"playing": False}
        meta = self._items[self._index]
        # progress_ms reste 0 ici (lecture synchrone) ; current_live() lit la
        # progression reelle via mpv (time-pos) de maniere async.
        return {
            "playing": (not self._paused) and self.is_playing,
            "title": meta.get("title", ""),
            "artist": meta.get("artist", ""),
            "album": meta.get("album", ""),
            "cover": meta.get("cover"),
            "uri": meta.get("uri", ""),
            "progress_ms": 0,
            "duration_ms": meta.get("duration_ms", 0),
        }

    async def current_live(self) -> dict:
        """Variante async de current() qui lit time-pos/duration depuis mpv."""
        base = self.current()
        if not base.get("playing") and not self._items:
            return base
        try:
            pos = await self._get_property("time-pos")
            dur = await self._get_property("duration")
            if pos is not None:
                base["progress_ms"] = int(float(pos) * 1000)
            if dur:
                base["duration_ms"] = int(float(dur) * 1000)
        except Exception:
            pass
        return base

    def upcoming(self) -> list[dict]:
        """File a venir -> [{title, artist, cover}]."""
        if not self._items:
            return []
        tail = self._items[self._index + 1:]
        return [
            {
                "title": it.get("title", ""),
                "artist": it.get("artist", ""),
                "cover": it.get("cover"),
            }
            for it in tail
        ]

    @property
    def is_playing(self) -> bool:
        """Vrai si mpv tourne avec une file chargee et non en pause."""
        alive = self._proc is not None and self._proc.returncode is None
        return alive and bool(self._items) and not self._paused

    async def shutdown(self) -> None:
        """Arret propre : annule le poll et termine mpv (au shutdown du backend)."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except Exception:
                pass
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                    await asyncio.wait_for(self._proc.wait(), timeout=2)
                except Exception:
                    pass
        self._proc = None
        logger.info("[MUSIC] mpv arrete (shutdown)")