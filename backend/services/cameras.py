import asyncio
import base64
import logging
import ssl
import time
from typing import Any

import requests

from config import UNIFI_HOST, UNIFI_USER, UNIFI_PASS, UNIFI_MAC

logger = logging.getLogger(__name__)

# Disable SSL warnings for self-signed certs
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CameraService:
    def __init__(self):
        self._session = requests.Session()
        self._session.verify = False
        self._host = UNIFI_HOST          # peut changer (DHCP) -> auto-redecouverte
        self._cameras: list[dict] = []
        self._authenticated = False
        self._last_auth = 0
        self._last_auth_attempt = 0      # backoff des tentatives de login (succes ou echec)
        self._last_discover = 0          # throttle du ping-sweep /24 (NVR injoignable)
        # requests.Session n'est pas thread-safe : on serialise les appels executor
        self._http_lock = asyncio.Lock()

    @property
    def _base_url(self) -> str:
        return f"https://{self._host}"

    def _local_prefix(self) -> str | None:
        """Prefixe /24 local (ex: '192.168.1')."""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local = s.getsockname()[0]
            s.close()
            return local.rsplit(".", 1)[0]
        except Exception:
            return None

    def _discover_controller(self) -> str | None:
        """Retrouve le controleur UniFi (NVR) meme si son IP a change (DHCP).

        1) Par MAC (UNIFI_MAC) : ping-sweep du /24 pour peupler la table ARP,
           puis on lit `ip neigh` et on matche la MAC — increvable, comme la
           domotique. 2) Repli : signature HTTP UniFi OS. Renvoie l'IP ou None.
        """
        import subprocess
        import concurrent.futures

        # Throttle : un ping-sweep /24 (254 IPs) est couteux. Quand le NVR est
        # injoignable, get_cameras peut re-tenter a chaque poll WS de l'UI -> on
        # cap les sweeps a ~1/min.
        now = time.time()
        if now - self._last_discover < 60:
            return None
        self._last_discover = now

        prefix = self._local_prefix()
        if not prefix:
            return None
        ips = [f"{prefix}.{i}" for i in range(1, 255)]

        # 1) Decouverte par MAC (preferee)
        target = (UNIFI_MAC or "").replace(":", "").replace("-", "").lower()
        if target:
            def _ping(ip: str):
                try:
                    subprocess.run(["ping", "-c", "1", "-W", "1", ip],
                                   capture_output=True, timeout=2)
                except Exception:
                    pass
            with concurrent.futures.ThreadPoolExecutor(max_workers=60) as ex:
                list(ex.map(_ping, ips))
            try:
                out = subprocess.run(["ip", "neigh"], capture_output=True,
                                     text=True, timeout=5).stdout
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and "lladdr" in parts and parts[0].startswith(prefix):
                        mac = parts[parts.index("lladdr") + 1].replace(":", "").lower()
                        if mac == target:
                            logger.info("[CAMERAS] Controleur trouve par MAC: %s", parts[0])
                            return parts[0]
            except Exception as e:
                logger.warning("[CAMERAS] Scan MAC KO: %s", e)

        # 2) Repli : signature HTTP UniFi OS
        def _probe(ip: str) -> str | None:
            try:
                r = requests.get(f"https://{ip}/", verify=False, timeout=1.5)
                if "unifi os" in r.text[:3000].lower():
                    p = requests.get(f"https://{ip}/proxy/protect/api/", verify=False, timeout=1.5)
                    if p.status_code in (200, 401):
                        return ip
            except Exception:
                pass
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=40) as ex:
            for fut in concurrent.futures.as_completed([ex.submit(_probe, ip) for ip in ips]):
                if fut.result():
                    return fut.result()
        return None

    async def start(self):
        if not UNIFI_USER or not UNIFI_PASS:
            logger.info("[CAMERAS] Pas de credentials UniFi — mode desactive")
            return
        loop = asyncio.get_event_loop()
        try:
            async with self._http_lock:
                await loop.run_in_executor(None, self._authenticate)
                await loop.run_in_executor(None, self._fetch_cameras)
            logger.info("[CAMERAS] %d cameras detectees", len(self._cameras))
        except Exception as e:
            logger.error("[CAMERAS] Erreur init: %s", e)

    def _login_once(self) -> bool:
        try:
            resp = self._session.post(
                f"{self._base_url}/api/auth/login",
                json={"username": UNIFI_USER, "password": UNIFI_PASS},
                timeout=8,
            )
            if resp.status_code == 200:
                self._authenticated = True
                self._last_auth = time.time()
                logger.info("[CAMERAS] Authentification reussie (%s)", self._host)
                return True
            logger.error("[CAMERAS] Auth echouee: %d", resp.status_code)
        except Exception as e:
            logger.warning("[CAMERAS] Connexion %s KO: %s", self._host, e)
        self._authenticated = False
        return False

    def _authenticate(self):
        if self._login_once():
            return
        # Echec (souvent : le NVR a change d'IP via DHCP) -> on rescanne le reseau.
        logger.warning("[CAMERAS] Auth KO sur %s — recherche du controleur UniFi...", self._host)
        found = self._discover_controller()
        if found and found != self._host:
            logger.info("[CAMERAS] Controleur UniFi redecouvert: %s -> %s", self._host, found)
            self._host = found
            self._login_once()

    def _ensure_auth(self):
        """Re-authenticate if session is older than 1 hour.

        Backoff : ne pas re-tenter un login (potentiellement un ping-sweep /24)
        plus d'une fois toutes les 30 s quand le NVR est down -> evite que la
        boucle MJPEG / les polls WS hammerent /api/auth/login.
        """
        if self._authenticated and (time.time() - self._last_auth <= 3600):
            return
        if time.time() - self._last_auth_attempt < 30:
            return
        self._last_auth_attempt = time.time()
        self._authenticate()

    def _fetch_cameras(self):
        self._ensure_auth()
        if not self._authenticated:
            return
        try:
            resp = self._session.get(
                f"{self._base_url}/proxy/protect/api/cameras",
                timeout=10,
            )
            if resp.status_code in (401, 403):
                # Session stale (reboot NVR, rotation token) -> forcer un re-login
                self._authenticated = False
                self._last_auth = 0
                logger.warning("[CAMERAS] Session invalide (%d) — re-auth au prochain appel", resp.status_code)
                return
            if resp.status_code == 200:
                data = resp.json()
                # Tolerer une enveloppe dict ({'data':[...]} / {'cameras':[...]})
                if isinstance(data, dict):
                    data = data.get("data") or data.get("cameras") or []
                if not isinstance(data, list):
                    logger.error("[CAMERAS] Forme inattendue de la liste: %s", type(data).__name__)
                    data = []
                self._cameras = [
                    {
                        "id": cam["id"],
                        "name": cam.get("name", "Camera"),
                        "type": cam.get("type", ""),
                        "state": cam.get("state", ""),
                        "mac": cam.get("mac", ""),
                    }
                    for cam in data
                    if isinstance(cam, dict) and cam.get("id") and cam.get("state") == "CONNECTED"
                ]
            else:
                logger.error("[CAMERAS] Erreur liste: %d", resp.status_code)
        except Exception as e:
            logger.error("[CAMERAS] Erreur fetch cameras: %s", e)

    async def get_cameras(self) -> list[dict]:
        if not self._cameras:
            loop = asyncio.get_event_loop()
            async with self._http_lock:
                await loop.run_in_executor(None, self._fetch_cameras)
        return self._cameras

    async def get_snapshot(self, camera_id: str) -> str | None:
        """Get a JPEG snapshot as base64 string."""
        loop = asyncio.get_event_loop()
        try:
            async with self._http_lock:
                return await loop.run_in_executor(None, self._fetch_snapshot, camera_id)
        except Exception as e:
            logger.error("[CAMERAS] Erreur snapshot %s: %s", camera_id, e)
            return None

    def _fetch_snapshot(self, camera_id: str) -> str | None:
        self._ensure_auth()
        if not self._authenticated:
            return None
        try:
            resp = self._session.get(
                f"{self._base_url}/proxy/protect/api/cameras/{camera_id}/snapshot",
                params={"force": "true", "w": 640, "h": 360},
                timeout=10,
            )
            if resp.status_code in (401, 403):
                self._authenticated = False
                self._last_auth = 0
                logger.warning("[CAMERAS] Snapshot %s: session invalide (%d) — re-auth au prochain appel", camera_id, resp.status_code)
                return None
            if resp.status_code == 200 and resp.content:
                return base64.b64encode(resp.content).decode("ascii")
            logger.warning("[CAMERAS] Snapshot %s: status %d", camera_id, resp.status_code)
            return None
        except Exception as e:
            logger.error("[CAMERAS] Erreur snapshot fetch: %s", e)
            return None

    async def get_all_snapshots(self) -> list[dict]:
        """Get snapshots for all cameras in parallel."""
        cameras = await self.get_cameras()
        snapshots = await asyncio.gather(
            *[self.get_snapshot(cam["id"]) for cam in cameras]
        )
        return [{**cam, "snapshot": snap} for cam, snap in zip(cameras, snapshots)]

    def _fetch_snapshot_raw(self, camera_id: str) -> bytes | None:
        """Get raw JPEG bytes (for MJPEG stream)."""
        self._ensure_auth()
        if not self._authenticated:
            return None
        try:
            resp = self._session.get(
                f"{self._base_url}/proxy/protect/api/cameras/{camera_id}/snapshot",
                params={"force": "true", "w": 1280, "h": 720},
                timeout=10,
            )
            if resp.status_code in (401, 403):
                self._authenticated = False
                self._last_auth = 0
                return None
            if resp.status_code == 200 and resp.content:
                return resp.content
            return None
        except Exception:
            return None

    async def stream_mjpeg(self, camera_id: str):
        """Async generator yielding MJPEG frames."""
        loop = asyncio.get_event_loop()
        while True:
            async with self._http_lock:
                frame = await loop.run_in_executor(None, self._fetch_snapshot_raw, camera_id)
            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
                    + frame + b"\r\n"
                )
            await asyncio.sleep(0.1)  # Small pause between fetches

    @property
    def available(self) -> bool:
        return bool(UNIFI_USER and UNIFI_PASS)
