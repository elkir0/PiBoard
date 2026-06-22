"""UPnP/DLNA player — sends audio URLs directly to Devialet.

The Devialet fetches the audio itself (0% CPU on Pi).
For local files, serves them via the FastAPI static server.
"""

import asyncio
import logging
import shutil
import uuid
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

logger = logging.getLogger(__name__)

try:
    import upnpclient
    HAS_UPNP = True
except ImportError:
    HAS_UPNP = False
    logger.warning("[UPNP] upnpclient non disponible — pip install upnpclient")

from config import DEVIALET_IP

# Local files served from frontend/dist (FastAPI serves this dir)
SERVE_DIR = Path(__file__).parent / ".." / ".." / "frontend" / "dist" / "upnp_audio"
SERVE_DIR.mkdir(exist_ok=True)

# Devialet UPnP device (cached)
_device = None
_device_url = None


def _discover_url() -> str:
    """Find Devialet UPnP MediaRenderer URL via SSDP."""
    import socket
    msg = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 3\r\n"
        "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n"
        "\r\n"
    )
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.settimeout(5)
    try:
        s.sendto(msg.encode(), ("239.255.255.250", 1900))
        while True:
            try:
                data, addr = s.recvfrom(4096)
                text = data.decode("utf-8", "ignore")
                if DEVIALET_IP in text:
                    for line in text.split("\r\n"):
                        if line.lower().startswith("location:"):
                            return line.split(":", 1)[1].strip()
            except socket.timeout:
                break
        return ""
    finally:
        s.close()


def _get_device():
    """Get UPnP device, re-discover if connection fails."""
    global _device, _device_url
    if not HAS_UPNP:
        return None

    # Try cached device first
    if _device is not None:
        try:
            _device.AVTransport  # Quick check if still valid
            return _device
        except Exception:
            logger.info("[UPNP] Device cache invalide, re-decouverte...")
            _device = None
            _device_url = None

    # Discover fresh
    try:
        _device_url = _discover_url()
        if _device_url:
            _device = upnpclient.Device(_device_url)
            logger.info("[UPNP] Devialet connecte: %s (%s)", _device.friendly_name, _device_url)
    except Exception as e:
        logger.warning("[UPNP] Erreur connexion: %s", e)
        _device = None
    return _device


def _didl_metadata(title: str, url: str, mime: str = "audio/mpeg") -> str:
    """Build DIDL-Lite XML metadata for UPnP SetAVTransportURI."""
    # title et url sont du contenu texte d'éléments (<dc:title>, <res>) :
    # échapper & < > sinon un titre type 'AC/DC - Rock & Roll' casse le DIDL.
    safe_title = _xml_escape(title)
    safe_url = _xml_escape(url)
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="0" parentID="0" restricted="1">'
        f'<dc:title>{safe_title}</dc:title>'
        '<upnp:class>object.item.audioItem.musicTrack</upnp:class>'
        f'<res protocolInfo="http-get:*:{mime}:*">{safe_url}</res>'
        '</item></DIDL-Lite>'
    )


async def play_url(url: str, title: str = "PI-Board", mime: str = "audio/mpeg") -> bool:
    """Send a URL to the Devialet for playback via UPnP.

    The URL must be reachable by the Devialet (HTTP on LAN, not HTTPS).
    """
    loop = asyncio.get_event_loop()
    try:
        def _play():
            dev = _get_device()
            if not dev:
                return False
            metadata = _didl_metadata(title, url, mime)
            dev.AVTransport.SetAVTransportURI(
                InstanceID=0, CurrentURI=url, CurrentURIMetaData=metadata
            )
            dev.AVTransport.Play(InstanceID=0, Speed="1")
            return True

        ok = await loop.run_in_executor(None, _play)
        if ok:
            logger.info("[UPNP] Play: %s (%s)", title, url[:60])
        return ok
    except Exception as e:
        logger.error("[UPNP] Erreur play: %s", e)
        return False


async def play_file(file_path: str, title: str = "PI-Board", mime: str = "audio/wav") -> bool:
    """Serve a local audio file via FastAPI and play it on the Devialet.

    Copies the file to frontend/dist/upnp_audio/ so FastAPI can serve it.
    """
    src = Path(file_path)
    if not src.exists():
        logger.error("[UPNP] Fichier introuvable: %s", file_path)
        return False

    # Copy to served directory with unique name
    fname = f"{uuid.uuid4().hex[:8]}{src.suffix}"
    dest = SERVE_DIR / fname
    shutil.copy2(src, dest)

    # Build URL reachable by Devialet
    from config import BACKEND_PORT
    import socket
    pi_ip = _get_pi_ip()
    url = f"http://{pi_ip}:{BACKEND_PORT}/upnp_audio/{fname}"

    ok = await play_url(url, title=title, mime=mime)

    # Clean up after a delay (let Devialet finish fetching)
    async def _cleanup():
        await asyncio.sleep(30)
        dest.unlink(missing_ok=True)
    asyncio.create_task(_cleanup())

    return ok


async def stop() -> bool:
    """Stop UPnP playback."""
    loop = asyncio.get_event_loop()
    try:
        def _stop():
            dev = _get_device()
            if dev:
                dev.AVTransport.Stop(InstanceID=0)
                return True
            return False
        return await loop.run_in_executor(None, _stop)
    except Exception as e:
        logger.error("[UPNP] Erreur stop: %s", e)
        return False


async def set_volume(percent: int) -> bool:
    """Set Devialet volume via UPnP."""
    loop = asyncio.get_event_loop()
    try:
        def _vol():
            dev = _get_device()
            if dev:
                dev.RenderingControl.SetVolume(
                    InstanceID=0, Channel="Master", DesiredVolume=max(0, min(100, percent))
                )
                return True
            return False
        return await loop.run_in_executor(None, _vol)
    except Exception as e:
        logger.error("[UPNP] Erreur volume: %s", e)
        return False


def _get_pi_ip() -> str:
    """Get the Pi's LAN IP address."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((DEVIALET_IP, 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"  # repli neutre (loopback), plus d'IP LAN codee en dur
