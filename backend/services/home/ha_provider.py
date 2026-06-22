"""Provider domotique HOME ASSISTANT — s'appuie sur une instance HA via son API REST.

Permet de profiter des milliers d'intégrations de Home Assistant : PI-Board
devient la belle façade salon, HA reste le cerveau domotique. Chaque appareil du
registre (`home.devices`) doit porter un `ha_entity` (ex `cover.volet_gauche`,
`switch.guinguette`, `button.portail`) et un `kind` (cover/gate/switch).

Config : `HA_URL` (ex http://homeassistant.local:8123) + `HA_TOKEN` (jeton d'accès
longue durée, Profil HA → Jetons). Zéro-crash : sans URL/token, domotique HA off.

⚠️ Implémenté mais NON validé en réel ici (nécessite une instance HA). Voir la
roadmap : à valider avec l'utilisateur.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from .base import HomeProvider, load_registry

logger = logging.getLogger(__name__)
_TIMEOUT = 8.0


class HomeAssistantProvider(HomeProvider):
    def __init__(self) -> None:
        try:
            from config import HA_URL, HA_TOKEN
        except Exception:
            HA_URL = HA_TOKEN = ""
        self._url = (HA_URL or "").rstrip("/")
        self._token = HA_TOKEN or ""
        # Registre {id: {name, kind, entity}} (appareils avec un ha_entity).
        self._devices: dict[str, dict] = {}
        for d in load_registry():
            did, ent = d.get("id"), d.get("ha_entity")
            if did and ent:
                self._devices[did] = {"name": d.get("name", did),
                                      "kind": d.get("kind", "switch"), "entity": ent}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def _call_service(self, domain: str, service: str, entity_id: str, data: dict | None = None) -> bool:
        if not self._url or not entity_id:
            return False
        try:
            payload = {"entity_id": entity_id, **(data or {})}
            async with httpx.AsyncClient(timeout=httpx.Timeout(_TIMEOUT)) as c:
                r = await c.post(f"{self._url}/api/services/{domain}/{service}",
                                 headers=self._headers(), json=payload)
                r.raise_for_status()
            logger.info("[HOME-HA] %s.%s %s", domain, service, entity_id)
            return True
        except Exception as e:
            logger.warning("[HOME-HA] %s.%s %s: %s", domain, service, entity_id, e)
            return False

    async def _state(self, entity_id: str) -> dict | None:
        if not self._url:
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(6)) as c:
                r = await c.get(f"{self._url}/api/states/{entity_id}", headers=self._headers())
                r.raise_for_status()
                return r.json()
        except Exception:
            return None

    # ------------------------------------------------------------------ start / status
    async def start(self) -> None:
        if not self._url or not self._token:
            logger.warning("[HOME-HA] HA_URL/HA_TOKEN manquants — domotique HA désactivée")
            return
        if not self._devices:
            logger.info("[HOME-HA] aucun appareil avec 'ha_entity' dans home.devices")
            return
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(6)) as c:
                r = await c.get(f"{self._url}/api/", headers=self._headers())
            if r.status_code == 200:
                logger.info("[HOME-HA] connecté à %s (%d appareils)", self._url, len(self._devices))
            else:
                logger.warning("[HOME-HA] /api/ -> HTTP %s (token ?)", r.status_code)
        except Exception as e:
            logger.warning("[HOME-HA] injoignable %s: %s", self._url, e)

    async def get_status(self) -> dict:
        result = {}
        for did, d in self._devices.items():
            st = await self._state(d["entity"])
            base = {"name": d["name"], "kind": d["kind"], "type": "homeassistant"}
            if not st:
                result[did] = {**base, "online": False}
                continue
            state = st.get("state")
            attrs = st.get("attributes", {}) or {}
            entry = {**base, "online": state not in ("unavailable", "unknown", None)}
            if d["kind"] == "cover":
                entry["state"] = state  # open/closed/opening/closing
                if "current_position" in attrs:
                    entry["position"] = attrs["current_position"]
            else:
                entry["on"] = (state == "on")
            result[did] = entry
        return result

    # ------------------------------------------------------------------ covers
    def _cover_entity(self, device_id: str) -> str | None:
        d = self._devices.get(device_id)
        return d["entity"] if d and d["kind"] == "cover" else None

    async def roller_open(self, device_id: str) -> bool:
        e = self._cover_entity(device_id)
        return await self._call_service("cover", "open_cover", e) if e else False

    async def roller_close(self, device_id: str) -> bool:
        e = self._cover_entity(device_id)
        return await self._call_service("cover", "close_cover", e) if e else False

    async def roller_stop(self, device_id: str) -> bool:
        e = self._cover_entity(device_id)
        return await self._call_service("cover", "stop_cover", e) if e else False

    async def roller_position(self, device_id: str, pos: int) -> bool:
        e = self._cover_entity(device_id)
        return await self._call_service("cover", "set_cover_position", e,
                                        {"position": max(0, min(100, int(pos)))}) if e else False

    async def open_all_rollers(self) -> bool:
        ids = [i for i, d in self._devices.items() if d["kind"] == "cover"]
        return all(await asyncio.gather(*(self.roller_open(i) for i in ids))) if ids else False

    async def close_all_rollers(self) -> bool:
        ids = [i for i, d in self._devices.items() if d["kind"] == "cover"]
        return all(await asyncio.gather(*(self.roller_close(i) for i in ids))) if ids else False

    # ------------------------------------------------------------------ gate (impulsion)
    async def trigger_portail(self) -> bool:
        ok = False
        for did, d in self._devices.items():
            if d["kind"] != "gate":
                continue
            ent = d["entity"]
            domain = ent.split(".")[0]
            if domain == "button":
                r = await self._call_service("button", "press", ent)
            elif domain == "cover":
                r = await self._call_service("cover", "open_cover", ent)
            elif domain == "scene":
                r = await self._call_service("scene", "turn_on", ent)
            else:  # switch impulsionnel
                r = await self._call_service("switch", "turn_on", ent)
            ok = ok or r
        return ok

    # ------------------------------------------------------------------ switch / plug
    async def _switch(self, device_id: str | None, service: str) -> bool:
        did = device_id if device_id in self._devices else \
            next((i for i, d in self._devices.items() if d["kind"] == "switch"), None)
        d = self._devices.get(did) if did else None
        if not d:
            return False
        ent = d["entity"]
        domain = ent.split(".")[0]
        if domain not in ("switch", "light", "input_boolean", "fan"):
            domain = "switch"
        return await self._call_service(domain, service, ent)

    async def plug_on(self, device_id: str = "guinguette") -> bool:
        return await self._switch(device_id, "turn_on")

    async def plug_off(self, device_id: str = "guinguette") -> bool:
        return await self._switch(device_id, "turn_off")

    async def plug_toggle(self, device_id: str = "guinguette") -> bool:
        return await self._switch(device_id, "toggle")
