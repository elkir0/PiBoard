"""Devialet IP Control API wrapper — async, zero-crash."""

import asyncio
import functools
import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

from config import DEVIALET_IP

logger = logging.getLogger(__name__)
_TIMEOUT = 2


def _prefix(msg: str) -> str:
    return f"[DEVIALET] {msg}"


class DevialetService:
    """Async wrapper around the Devialet IP Control REST API."""

    def __init__(self, ip: Optional[str] = None):
        self.ip = ip or DEVIALET_IP
        self.base = f"http://{self.ip}/ipcontrol/v1"
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_volume: Optional[int] = None
        # Session reutilisee (keep-alive) : get_status emet 7 requetes en burst
        # -> pool dimensionne pour eviter le warning "Connection pool is full".
        self._session = requests.Session()
        _adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8)
        self._session.mount("http://", _adapter)
        self._session.mount("https://", _adapter)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _vol_int(v) -> Optional[int]:
        """Normalise un volume API (peut etre float 58.5) en int coherent.
        Retourne None si non convertible (zero-crash)."""
        if v is None:
            return None
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.get_event_loop()
        return self._loop

    async def _get(self, path: str) -> Optional[dict]:
        url = f"{self.base}{path}"
        try:
            resp = await self._get_loop().run_in_executor(
                None, functools.partial(self._session.get, url, timeout=_TIMEOUT)
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(_prefix(f"GET {path} failed: {exc}"))
            return None

    async def _post(self, path: str, body: Optional[dict] = None) -> bool:
        url = f"{self.base}{path}"
        try:
            resp = await self._get_loop().run_in_executor(
                None,
                functools.partial(
                    self._session.post, url, json=body or {}, timeout=_TIMEOUT
                ),
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning(_prefix(f"POST {path} failed: {exc}"))
            return False

    # ------------------------------------------------------------------
    # 1. Start / connectivity
    # ------------------------------------------------------------------

    async def start(self) -> bool:
        """Test connectivity and cache current volume."""
        info = await self._get("/devices/current")
        if info:
            name = info.get("deviceName", "?")
            model = info.get("model", "?")
            logger.info(_prefix(f"Connected — {model} '{name}' at {self.ip}"))
            # Cache current Devialet volume so ensure_volume works from start
            vol_data = await self._get("/systems/current/sources/current/soundControl/volume")
            if vol_data and self._vol_int(vol_data.get("volume")) is not None:
                self._last_volume = self._vol_int(vol_data["volume"])
                logger.info(_prefix(f"Volume initial: {self._last_volume}%"))
            else:
                self._last_volume = 40  # Safe default
                logger.info(_prefix("Pas de source active, volume par defaut: 40%"))
            return True
        logger.error(_prefix(f"Cannot reach Devialet at {self.ip}"))
        return False

    # ------------------------------------------------------------------
    # 2. Status (aggregate)
    # ------------------------------------------------------------------

    async def get_status(self) -> dict:
        """Return a combined status dict (device, source, volume, etc.)."""
        device, system, source, vol, night, eq = await asyncio.gather(
            self._get("/devices/current"),
            self._get("/systems/current"),
            self._get("/groups/current/sources/current"),
            self._get("/systems/current/sources/current/soundControl/volume"),
            self._get("/systems/current/settings/audio/nightMode"),
            self._get("/systems/current/settings/audio/equalizer"),
        )
        connected = device is not None
        # SOURCE DE VÉRITÉ : on re-aligne le cache sur le volume REEL de l'appareil
        # a chaque status/poll -> adjust_output_volume et ensure_volume ne partent
        # plus jamais d'une valeur perimee (corrige les sauts de volume).
        if vol and self._vol_int(vol.get("volume")) is not None:
            self._last_volume = self._vol_int(vol["volume"])
        fw = (device or {}).get("release", {})
        # Source type-gardee : l'API peut renvoyer source={'source':'<str>'} ou
        # une liste selon le firmware/AirPlay -> ne pas appeler .get sur un non-dict.
        _src = (source or {}).get("source") if isinstance(source, dict) else None
        current_source = _src.get("type") if isinstance(_src, dict) else None
        return {
            "connected": connected,
            "model": (device or {}).get("model", ""),
            "systemName": (system or {}).get("systemName", "Devialet"),
            "firmware": fw.get("version", "") if isinstance(fw, dict) else str(fw),
            "volume": self._vol_int((vol or {}).get("volume")) if vol else None,
            "nightMode": (night or {}).get("nightMode") == "on" if night else False,
            "eqPreset": (eq or {}).get("preset", "flat"),
            "currentSource": current_source,
            "playingState": (source or {}).get("playingState"),
            "muteState": (source or {}).get("muteState"),
            "metadata": (source or {}).get("metadata"),
            "sources": [s.get("type") for s in ((await self.get_sources()) or [])],
            "devices": [
                {
                    "name": d.get("deviceName", ""),
                    "role": d.get("role", ""),
                    "serial": d.get("serial", ""),
                    "isLeader": d.get("isSystemLeader", False),
                }
                for d in (system or {}).get("devices", [])
            ],
        }

    # ------------------------------------------------------------------
    # 3-4. Volume
    # ------------------------------------------------------------------

    async def set_volume(self, percent: int) -> bool:
        """Set volume (0-100) on Devialet only. PipeWire stays at 100%."""
        percent = max(0, min(100, percent))
        ok = await self._post(
            "/systems/current/sources/current/soundControl/volume",
            {"volume": percent},
        )
        # N'ecrire le cache qu'apres POST reussi : sur echec (veille, reseau,
        # timeout) on conserve la derniere valeur connue-bonne (pas de poison).
        if ok:
            self._last_volume = percent
        return ok

    async def get_volume_fresh(self) -> Optional[int]:
        """Lit le volume REEL de l'appareil (GET leger) et rafraichit le cache.
        Retourne None UNIQUEMENT si le GET echoue (pas de fallback cache) : les
        appelants peuvent ainsi distinguer une vraie valeur d'un cache perime et
        eviter un set absolu base sur une valeur stale (saut de volume)."""
        data = await self._get("/systems/current/sources/current/soundControl/volume")
        if data:
            vol = self._vol_int(data.get("volume"))
            if vol is not None:
                self._last_volume = vol
                return vol
        return None

    async def get_volume(self) -> Optional[int]:
        """Lit le volume REEL de l'appareil (GET leger) et rafraichit le cache.
        SOURCE DE VERITE pour les increments relatifs (monte/baisse le son).
        Si le GET echoue, retombe sur le cache (possiblement perime)."""
        vol = await self.get_volume_fresh()
        if vol is not None:
            return vol
        logger.warning(_prefix(f"GET volume echoue, fallback cache: {self._last_volume}"))
        return self._last_volume

    async def ensure_volume(self):
        """Re-aligne le cache sur le volume REEL de l'appareil au changement de
        piste. NE re-pousse PLUS une valeur de cache (ca pouvait ecraser un reglage
        manuel externe). N'ecrit PAS non plus le sink PipeWire (sur un RAOP, le
        volume du sink EST le volume AirPlay -> double-ecriture = saut)."""
        await self.get_volume()

    async def volume_up(self) -> bool:
        return await self._post(
            "/systems/current/sources/current/soundControl/volumeUp"
        )

    async def volume_down(self) -> bool:
        return await self._post(
            "/systems/current/sources/current/soundControl/volumeDown"
        )

    # ------------------------------------------------------------------
    # 4b. Power management (IP Control n'expose QUE powerOff = mise en veille ;
    # pas de reboot ni de power-on cote API — le Phantom se reveille a la 1ere
    # lecture AirPlay. Le "redemarrage" = veille + reveil par l'audio.)
    # ------------------------------------------------------------------

    async def power_off(self) -> bool:
        """Met le systeme Devialet en veille (POST /systems/current/powerOff)."""
        return await self._post("/systems/current/powerOff")

    # ------------------------------------------------------------------
    # 5. Playback
    # ------------------------------------------------------------------

    async def play(self) -> bool:
        return await self._post("/groups/current/sources/current/playback/play")

    async def pause(self) -> bool:
        return await self._post("/groups/current/sources/current/playback/pause")

    async def next_track(self) -> bool:
        return await self._post("/groups/current/sources/current/playback/next")

    async def previous_track(self) -> bool:
        return await self._post(
            "/groups/current/sources/current/playback/previous"
        )

    # ------------------------------------------------------------------
    # 6. Mute
    # ------------------------------------------------------------------

    async def mute(self) -> bool:
        return await self._post("/groups/current/sources/current/playback/mute")

    async def unmute(self) -> bool:
        return await self._post(
            "/groups/current/sources/current/playback/unmute"
        )

    # ------------------------------------------------------------------
    # 7. Night mode
    # ------------------------------------------------------------------

    async def set_night_mode(self, on: bool) -> bool:
        return await self._post(
            "/systems/current/settings/audio/nightMode",
            {"nightMode": "on" if on else "off"},
        )

    # ------------------------------------------------------------------
    # 8-9. Equalizer
    # ------------------------------------------------------------------

    async def get_equalizer(self) -> Optional[dict]:
        return await self._get("/systems/current/settings/audio/equalizer")

    async def set_equalizer_preset(self, preset: str) -> bool:
        """Set EQ preset: flat, custom, voice, etc."""
        return await self._post(
            "/systems/current/settings/audio/equalizer",
            {"preset": preset},
        )

    # ------------------------------------------------------------------
    # 10-11. Sources
    # ------------------------------------------------------------------

    async def get_sources(self) -> Optional[list]:
        data = await self._get("/groups/current/sources")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("sources", [])
        return None

    async def get_current_source(self) -> Optional[dict]:
        return await self._get("/groups/current/sources/current")
