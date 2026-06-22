import asyncio
import functools
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Config (source de verite de la sortie choisie). Import defensif.
try:
    from admin.config_manager import config as _config
except Exception:  # pragma: no cover
    _config = None


async def _list_sinks() -> list[str]:
    """Noms pactl de tous les sinks presents."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "list", "short", "sinks",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return [c[1] for c in (l.split("\t") for l in out.decode().splitlines()) if len(c) >= 2]
    except Exception:
        return []


async def find_devialet_sink() -> str | None:
    """Nom du sink RAOP Devialet (Phantom), resolu dynamiquement — son nom
    contient l'IP qui change via DHCP, donc on le retrouve a chaque fois."""
    for name in await _list_sinks():
        if "raop" in name.lower() and "phantom" in name.lower():
            return name
    return None


def is_devialet_sink(name: str | None) -> bool:
    return bool(name) and "raop" in name.lower() and "phantom" in name.lower()


def is_bluetooth_sink(name: str | None) -> bool:
    return bool(name) and name.lower().startswith("bluez_output")


async def find_bluez_sink(mac: str) -> str | None:
    """Sink PipeWire d'un peripherique BT connecte. On matche par MAC (en
    underscores majuscules) car le suffixe de profil varie (.1, .a2dp-sink...)."""
    token = mac.replace(":", "_").upper()
    for name in await _list_sinks():
        if "bluez_output" in name.lower() and token in name.upper():
            return name
    return None


async def resolve_output_sink() -> str | None:
    """SORTIE CHOISIE (source de verite unique) : lit config audio.output_sink ;
    si vide ou absent du systeme, fallback = Devialet. None si rien de jouable."""
    chosen = ""
    if _config is not None:
        try:
            chosen = _config.get("audio", "output_sink", "") or ""
        except Exception:
            chosen = ""
    if chosen and chosen in await _list_sinks():
        return chosen
    # vide, ou sink choisi disparu -> fallback Devialet
    return await find_devialet_sink()


async def ensure_selected_output() -> str | None:
    """Verrouille la SORTIE CHOISIE comme sink par defaut PipeWire. Remplace
    l'ancien 'Devialet en dur' : la sortie n'est plus codee en dur mais lue dans
    la config (fallback Devialet). Renvoie le nom du sink (ou None)."""
    sink = await resolve_output_sink()
    if not sink:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-default-sink", sink,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
    except Exception:
        pass
    return sink


# Compat : ancien nom encore reference ailleurs -> pointe vers la version configurable.
ensure_devialet_default = ensure_selected_output


async def get_named_sink_volume(sink: str) -> int:
    """Volume (%) d'un sink pactl nomme."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "get-sink-volume", sink,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        for part in out.decode().split("/"):
            part = part.strip()
            if part.endswith("%"):
                return int(part[:-1].strip())
    except Exception:
        pass
    return 50


async def set_named_sink_volume(sink: str, percent: int):
    """Regle le volume d'un sink pactl nomme (sorties locales type HDMI)."""
    percent = max(0, min(100, int(percent)))
    try:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-sink-volume", sink, f"{percent}%",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
    except Exception:
        pass


async def _get_sink_volume() -> int:
    """Read current PipeWire default sink volume percent."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "get-sink-volume", "@DEFAULT_SINK@",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        for part in stdout.decode().split('/'):
            part = part.strip()
            if part.endswith('%'):
                return int(part[:-1].strip())
    except Exception:
        pass
    return 50


async def _set_sink_volume(percent: int):
    """Set PipeWire default sink volume."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
    except Exception:
        pass


async def play_audio_file(file_path: str | Path):
    """Play an audio file via PipeWire (paplay) at the current Devialet volume level."""
    try:
        # Verrouille la SORTIE CHOISIE comme defaut ET cible-la explicitement :
        # le TTS suit toujours la sortie configuree (Devialet OU HDMI/local).
        sink = await ensure_selected_output()

        # paplay volume: 65536 = 100%.
        if is_devialet_sink(sink):
            # Devialet : cale le TTS sur le volume API Devialet (TTS ~ musique).
            devialet_vol = 50
            try:
                import requests
                from config import DEVIALET_IP
                # Appel HTTP synchrone deporte dans le thread-pool pour ne pas
                # bloquer l'event loop (~1s a chaque phrase TTS sinon).
                loop = asyncio.get_running_loop()
                r = await loop.run_in_executor(
                    None,
                    functools.partial(
                        requests.get,
                        f"http://{DEVIALET_IP}/ipcontrol/v1/systems/current/sources/current/soundControl/volume",
                        timeout=1,
                    ),
                )
                # Valide la valeur lue : un 'volume' null/string ne doit pas
                # casser le calcul plus bas (sinon TTS muet au lieu du fallback).
                vol = r.json().get("volume")
                if isinstance(vol, (int, float)) and not isinstance(vol, bool):
                    devialet_vol = vol
            except Exception:
                pass
            paplay_vol = max(6554, min(65536, int(65536 * devialet_vol / 100)))
        else:
            # Sortie locale (HDMI...) : le volume du sink gere le niveau -> TTS plein.
            devialet_vol = 100
            paplay_vol = 65536

        args = ["paplay", f"--volume={paplay_vol}"]
        if sink:
            args.append(f"--device={sink}")
        args.append(str(file_path))
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        logger.info("[OUTPUT] TTS joue (vol=%d, devialet=%d%%, sink=%s)",
                    paplay_vol, devialet_vol, sink or "default")
    except FileNotFoundError:
        logger.warning("[OUTPUT] paplay non disponible — audio non joue")
    except Exception as e:
        logger.error("[OUTPUT] Erreur lecture: %s", e)


async def play_audio_bytes(data: bytes, suffix: str = ".wav"):
    """Write audio bytes to temp file and play."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        tmp_path = f.name
    await play_audio_file(tmp_path)
    Path(tmp_path).unlink(missing_ok=True)
