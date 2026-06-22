"""Provider domotique LITE — drivers intégrés Shelly (rollers/cover/relais) + Kasa.

Aucune dépendance externe (pas de Home Assistant). Le registre d'appareils vient
de la config (`home.devices`, cf base.py), plus aucune adresse codée en dur : la
découverte scanne le /24 LOCAL (auto-détecté) et associe par MAC / id Shelly.
Registre vide = domotique désactivée proprement.

Drivers supportés : shelly_roller (Gen1), shelly_cover_g2 (Gen2 RPC),
shelly_relay_g3 (Gen3 RPC, portail impulsionnel), kasa_plug (python-kasa).
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from .base import HomeProvider, load_registry

logger = logging.getLogger(__name__)
_TIMEOUT = 3.0


def _local_prefix() -> str | None:
    """Préfixe /24 local (ex '192.168.1'). None si introuvable.

    1) Astuce UDP (interface de la route par défaut) — la plus fiable.
    2) Repli : 1ʳᵉ IPv4 non-loopback de l'hôte (`getaddrinfo`) — couvre le cas
       « LAN up mais pas encore de route par défaut » (Pi qui boote avant le DHCP),
       où l'astuce UDP échoue alors qu'on a déjà une IP exploitable.
    """
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            return ip.rsplit(".", 1)[0]
    except Exception:
        pass
    try:
        for *_, sa in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = sa[0]
            if not ip.startswith("127."):
                return ip.rsplit(".", 1)[0]
    except Exception:
        pass
    return None


class LiteHomeProvider(HomeProvider):
    def __init__(self) -> None:
        # Registre interne {id: {name, kind, driver, mac, shelly_id, ip}} depuis la config.
        self._devices: dict[str, dict] = {}
        for d in load_registry():
            did = d.get("id")
            if not did:
                continue
            self._devices[did] = {
                "name": d.get("name", did),
                "kind": d.get("kind", "switch"),
                "driver": d.get("driver", ""),
                "mac": (d.get("mac") or "").upper(),
                "shelly_id": d.get("shelly_id") or "",
                "ip": d.get("ip"),  # explicite si fourni, sinon auto-découvert
            }
        self._kasa = {}        # id -> SmartPlug
        self._kasa_lock = asyncio.Lock()

    # ------------------------------------------------------------------ helpers
    async def _http_get(self, url: str, timeout: float = _TIMEOUT):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as c:
                r = await c.get(url)
                r.raise_for_status()
                try:
                    return r.json()
                except Exception:
                    return {"ok": True}
        except Exception as exc:
            logger.warning("[HOME] GET %s: %s", url, exc)
            return None

    def _dev(self, device_id: str) -> dict | None:
        d = self._devices.get(device_id)
        if not d:
            logger.warning("[HOME] appareil inconnu: %s", device_id)
        return d

    def _by_kind(self, kind: str) -> list[str]:
        return [did for did, d in self._devices.items() if d.get("kind") == kind]

    def _first_switch(self, device_id: str | None) -> str | None:
        """Résout l'id d'une prise/relais (donné, sinon le 1er kind=switch)."""
        if device_id and device_id in self._devices:
            return device_id
        sw = self._by_kind("switch")
        return sw[0] if sw else None

    # ------------------------------------------------------------------ start / discovery
    async def start(self) -> None:
        if not self._devices:
            logger.info("[HOME] aucun appareil configuré (home.devices vide) — domotique désactivée")
            return
        await self._discover()
        for did, d in self._devices.items():
            # "OK" = on a une IP utilisable. Une prise Kasa sans IP (python-kasa
            # absent ou non découverte) doit afficher NON TROUVÉ, pas un faux OK.
            ok = bool(d.get("ip"))
            logger.info("[HOME] %s (%s) — %s", d["name"], d.get("ip") or "?", "OK" if ok else "NON TROUVÉ")

    def _shelly_pending(self) -> list[dict]:
        """Appareils Shelly déclarés (mac/id) encore sans IP."""
        return [d for d in self._devices.values()
                if d["driver"].startswith("shelly") and not d.get("ip")]

    async def _scan_shelly(self, prefix: str) -> None:
        """Une passe de balayage /24 (probe /shelly en parallèle, borné) qui
        renseigne l'IP des Shelly manquants par MAC / id."""
        sem = asyncio.Semaphore(50)

        async def probe(last: int):
            async with sem:
                data = await self._http_get(f"http://{prefix}.{last}/shelly", timeout=1.5)
            if isinstance(data, dict) and ("mac" in data or "id" in data):
                return f"{prefix}.{last}", (data.get("mac") or "").upper(), data.get("id") or ""
            return None

        results = await asyncio.gather(*(probe(i) for i in range(1, 255)))
        for res in results:
            if not res:
                continue
            ip, mac, sid = res
            for d in self._devices.values():
                if d.get("ip"):
                    continue
                if (d["mac"] and d["mac"] == mac) or (d["shelly_id"] and d["shelly_id"] == sid):
                    d["ip"] = ip

    async def _discover(self) -> None:
        # Shelly sans IP explicite : scan du /24 local. Une sonde unique rate
        # parfois un appareil un peu lent à répondre (vu sur le portail Gen3) ;
        # comme la découverte ne tourne qu'au boot, un appareil manqué resterait
        # injoignable jusqu'au prochain redémarrage. On re-balaye donc tant qu'il
        # en manque (max 3 passes ; on s'arrête dès que tout est résolu).
        if self._shelly_pending():
            prefix = _local_prefix()
            if prefix:
                for attempt in range(3):
                    if not self._shelly_pending():
                        break
                    if attempt:
                        logger.info("[HOME] re-scan Shelly (passe %d, %d manquant(s))",
                                    attempt + 1, len(self._shelly_pending()))
                    await self._scan_shelly(prefix)
            else:
                logger.warning("[HOME] préfixe LAN introuvable — pas de découverte Shelly")
        # Kasa via python-kasa (par nom/alias).
        if any(d["driver"] == "kasa_plug" for d in self._devices.values()):
            try:
                from kasa import Discover
                found = await Discover.discover(timeout=2)
                # Le raccourci « 1 seule prise configurée » n'est SÛR que s'il n'y a
                # aussi qu'une seule prise Kasa découverte ; sinon on exige le match
                # par alias, sans quoi la prise configurée se lierait arbitrairement
                # à la 1ʳᵉ Kasa énumérée (mauvais appareil sur un LAN multi-Kasa).
                single_kasa = len(found) == 1
                for addr, device in found.items():
                    try:
                        await device.update()
                    except Exception:
                        continue
                    alias = (device.alias or "").lower()
                    for did, d in self._devices.items():
                        if d["driver"] == "kasa_plug" and not d.get("ip") and \
                                (d["name"].lower() in alias or
                                 (single_kasa and len(self._by_kind("switch")) == 1)):
                            d["ip"] = addr
                            logger.info("[HOME] Kasa %s @ %s", device.alias, addr)
            except ImportError:
                logger.warning("[HOME] python-kasa non installé (prises Kasa indisponibles)")
            except Exception as e:
                logger.warning("[HOME] découverte Kasa: %s", e)

    async def _get_kasa(self, device_id: str):
        """SmartPlug connecté pour un appareil kasa (lazy). Caller tient le lock."""
        d = self._devices.get(device_id)
        ip = d.get("ip") if d else None
        if not ip:
            logger.warning("[HOME] Kasa %s : IP inconnue", device_id)
            return None
        plug = self._kasa.get(device_id)
        if plug is None or getattr(plug, "host", None) != ip:
            try:
                from kasa import SmartPlug
                plug = SmartPlug(ip)
                self._kasa[device_id] = plug
            except ImportError:
                logger.error("[HOME] python-kasa non installé")
                return None
        try:
            await plug.update()
        except Exception as exc:
            logger.warning("[HOME] Kasa update %s: %s", device_id, exc)
            return None
        return plug

    # ------------------------------------------------------------------ status
    async def get_status(self) -> dict:
        result = {}
        for did, dev in self._devices.items():
            ip, driver = dev.get("ip"), dev["driver"]
            base = {"name": dev["name"], "type": driver, "kind": dev["kind"]}
            try:
                if driver == "shelly_roller":
                    data = await self._http_get(f"http://{ip}/roller/0")
                    result[did] = {**base, "online": data is not None,
                                   "state": (data or {}).get("state"), "position": (data or {}).get("current_pos")}
                elif driver == "shelly_cover_g2":
                    data = await self._http_get(f"http://{ip}/rpc/Cover.GetStatus?id=0")
                    result[did] = {**base, "online": data is not None,
                                   "state": (data or {}).get("state"), "position": (data or {}).get("current_pos")}
                elif driver == "shelly_relay_g3":
                    data = await self._http_get(f"http://{ip}/rpc/Switch.GetStatus?id=0")
                    result[did] = {**base, "online": data is not None, "on": (data or {}).get("output", False)}
                elif driver == "kasa_plug":
                    async with self._kasa_lock:
                        plug = await self._get_kasa(did)
                    result[did] = {**base, "online": plug is not None, "on": plug.is_on if plug else None}
                else:
                    result[did] = {**base, "online": False}
            except Exception as exc:
                logger.warning("[HOME] status %s: %s", did, exc)
                result[did] = {**base, "online": False}
        return result

    # ------------------------------------------------------------------ covers
    async def _cover_cmd(self, device_id: str, action: str, pos: int | None = None) -> bool:
        dev = self._dev(device_id)
        if not dev or not dev.get("ip"):
            if dev:
                logger.warning("[HOME] %s — %s ÉCHEC (pas d'IP)", dev["name"], action)
            return False
        ip, driver = dev["ip"], dev["driver"]
        g2 = driver == "shelly_cover_g2"
        if action == "open":
            url = f"http://{ip}/rpc/Cover.Open?id=0" if g2 else f"http://{ip}/roller/0?go=open"
        elif action == "close":
            url = f"http://{ip}/rpc/Cover.Close?id=0" if g2 else f"http://{ip}/roller/0?go=close"
        elif action == "stop":
            url = f"http://{ip}/rpc/Cover.Stop?id=0" if g2 else f"http://{ip}/roller/0?go=stop"
        elif action == "position":
            p = max(0, min(100, int(pos or 0)))
            url = (f"http://{ip}/rpc/Cover.GoToPosition?id=0&pos={p}" if g2
                   else f"http://{ip}/roller/0?go=to_pos&roller_pos={p}")
        else:
            return False
        r = await self._http_get(url)
        logger.info("[HOME] %s — %s%s", dev["name"], action, "" if r is not None else " ÉCHEC")
        return r is not None

    async def roller_open(self, device_id: str) -> bool:
        return await self._cover_cmd(device_id, "open")

    async def roller_close(self, device_id: str) -> bool:
        return await self._cover_cmd(device_id, "close")

    async def roller_stop(self, device_id: str) -> bool:
        return await self._cover_cmd(device_id, "stop")

    async def roller_position(self, device_id: str, pos: int) -> bool:
        return await self._cover_cmd(device_id, "position", pos)

    async def open_all_rollers(self) -> bool:
        covers = self._by_kind("cover")
        if not covers:
            return False
        return all(await asyncio.gather(*(self.roller_open(c) for c in covers)))

    async def close_all_rollers(self) -> bool:
        covers = self._by_kind("cover")
        if not covers:
            return False
        return all(await asyncio.gather(*(self.roller_close(c) for c in covers)))

    # ------------------------------------------------------------------ gate (portail, impulsion)
    async def trigger_portail(self) -> bool:
        gates = self._by_kind("gate")
        ok = False
        for did in gates:
            dev = self._devices[did]
            if not dev.get("ip"):
                logger.warning("[HOME] %s — déclenchement ÉCHEC (pas d'IP)", dev["name"])
                continue
            # Impulsion auto-réarmée (toggle_after=1) : un seul aller-retour, pas de latch.
            r = await self._http_get(f"http://{dev['ip']}/rpc/Switch.Set?id=0&on=true&toggle_after=1")
            logger.info("[HOME] %s — impulsion%s", dev["name"], "" if r is not None else " ÉCHEC")
            ok = ok or (r is not None)
        return ok

    # ------------------------------------------------------------------ switch / plug (Kasa)
    async def _plug_set(self, device_id: str | None, action: str) -> bool:
        did = self._first_switch(device_id)
        dev = self._devices.get(did) if did else None
        if not dev or dev["driver"] != "kasa_plug":
            return False
        try:
            async with self._kasa_lock:
                plug = await self._get_kasa(did)
                if not plug:
                    return False
                if action == "on":
                    await plug.turn_on()
                elif action == "off":
                    await plug.turn_off()
                else:  # toggle
                    await (plug.turn_off() if plug.is_on else plug.turn_on())
                logger.info("[HOME] %s — %s", dev["name"], action.upper())
                return True
        except Exception as exc:
            logger.warning("[HOME] plug %s %s: %s", action, did, exc)
        return False

    async def plug_on(self, device_id: str = "guinguette") -> bool:
        return await self._plug_set(device_id, "on")

    async def plug_off(self, device_id: str = "guinguette") -> bool:
        return await self._plug_set(device_id, "off")

    async def plug_toggle(self, device_id: str = "guinguette") -> bool:
        return await self._plug_set(device_id, "toggle")
