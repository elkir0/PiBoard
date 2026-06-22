"""Gestion Bluetooth (enceintes) via bluetoothctl (BlueZ). Zero-crash, tout async.

On pilote bluetoothctl en sous-commandes one-shot (BlueZ 5.66) : aucune dependance
nouvelle, pas de D-Bus. Appairage 'Just Works' uniquement (enceintes a code PIN =
hors scope). Chaque fonction echoue en silence (log + valeur sure), jamais
d'exception qui remonte au main loop.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Icones BlueZ correspondant a une sortie audio (enceinte/casque).
_AUDIO_ICONS = {"audio-card", "audio-headset", "audio-headphones", "audio-speakers"}
_A2DP_UUID = "0000110b"  # Advanced Audio Distribution (Audio Sink)

# Process de decouverte temporisee en cours (bluetoothctl --timeout N scan on).
_scan_proc: "asyncio.subprocess.Process | None" = None

# SERIALISE les operations mutantes (pair/connect/disconnect/forget) : lancer
# plusieurs `bluetoothctl` concurrents sur le meme appareil les fait se telescoper
# (l'agent d'appairage est recree a chaque process) -> appairage corrompu /
# AuthenticationFailed / flapping. Un seul a la fois.
_op_lock = asyncio.Lock()


async def _run(args: list[str], timeout: float = 8.0) -> tuple[int, str]:
    """Execute `bluetoothctl <args>`. Renvoie (rc, stdout+stderr). Jamais d'exception."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return 124, ""
        return proc.returncode or 0, out.decode(errors="replace")
    except FileNotFoundError:
        logger.warning("[BLUETOOTH] bluetoothctl introuvable")
        return 127, ""
    except Exception as e:
        logger.error("[BLUETOOTH] erreur run %s: %s", args, e)
        return 1, ""


async def _session(steps: list, overall_timeout: float = 45.0) -> str:
    """Lance UNE session bluetoothctl interactive (agent persistant pendant TOUT
    l'echange) et envoie une sequence (cmd, delai_apres_en_s). Renvoie la sortie.
    C'est la recette fiable d'appairage : l'agent reste enregistre du debut a la
    fin, contrairement a des process one-shot separes. Jamais d'exception."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        logger.warning("[BLUETOOTH] bluetoothctl introuvable")
        return ""
    except Exception as e:
        logger.error("[BLUETOOTH] session impossible: %s", e)
        return ""

    chunks: list[str] = []

    async def _reader():
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                chunks.append(line.decode(errors="replace"))
        except Exception:
            pass

    async def _driver():
        for cmd, delay in steps:
            try:
                proc.stdin.write((cmd + "\n").encode())
                await proc.stdin.drain()
            except Exception:
                break
            await asyncio.sleep(delay)
        try:
            proc.stdin.write(b"quit\n")
            await proc.stdin.drain()
        except Exception:
            pass

    reader = asyncio.create_task(_reader())
    try:
        await asyncio.wait_for(_driver(), timeout=overall_timeout)
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        logger.error("[BLUETOOTH] session: %s", e)
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            await asyncio.wait_for(reader, timeout=2)
        except Exception:
            reader.cancel()
    return "".join(chunks)


def _last_line(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[-1] if lines else ""


async def is_available() -> bool:
    """Vrai si un controleur Bluetooth est present."""
    rc, out = await _run(["list"], timeout=5)
    return rc == 0 and "Controller" in out


def is_scanning() -> bool:
    return _scan_proc is not None and _scan_proc.returncode is None


async def power_on():
    """Allume le controleur (idempotent)."""
    await _run(["power", "on"], timeout=5)


def _parse_info(out: str) -> dict:
    """Parse la sortie de `bluetoothctl info <MAC>`."""
    info = {"name": "", "paired": False, "trusted": False,
            "connected": False, "icon": "", "audio": False}
    uuids = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Name:"):
            info["name"] = line.split(":", 1)[1].strip()
        elif line.startswith("Alias:") and not info["name"]:
            info["name"] = line.split(":", 1)[1].strip()
        elif line.startswith("Paired:"):
            info["paired"] = line.endswith("yes")
        elif line.startswith("Trusted:"):
            info["trusted"] = line.endswith("yes")
        elif line.startswith("Connected:"):
            info["connected"] = line.endswith("yes")
        elif line.startswith("Icon:"):
            info["icon"] = line.split(":", 1)[1].strip()
        elif line.startswith("UUID:"):
            uuids.append(line.lower())
    info["audio"] = (info["icon"] in _AUDIO_ICONS
                     or any(_A2DP_UUID in u for u in uuids))
    return info


async def list_devices(paired_only: bool = False, info_cap: int = 40) -> list[dict]:
    """Liste les appareils avec leur etat. Renvoie
    [{mac, name, paired, trusted, connected, icon, audio}].
    paired_only=True -> uniquement les appareils appaires/connus (petit ensemble,
    pour le monitor en regime permanent) ; sinon tout le cache de decouverte (UI
    scan), avec un plafond `info_cap` d'appels `info` pour ne pas saturer une piece
    pleine d'appareils."""
    rc, out = await _run(["devices", "Paired"] if paired_only else ["devices"], timeout=6)
    pending = []
    seen = set()
    for line in out.splitlines():
        line = line.strip()
        # Format : "Device AA:BB:CC:DD:EE:FF Nom de l'appareil"
        if not line.startswith("Device "):
            continue
        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
        mac = parts[1]
        if mac in seen or len(mac) != 17:
            continue
        seen.add(mac)
        pending.append((mac, parts[2] if len(parts) > 2 else mac))
    if len(pending) > info_cap:
        pending = pending[:info_cap]
    devices = []
    for mac, fallback_name in pending:
        _, info_out = await _run(["info", mac], timeout=5)
        info = _parse_info(info_out)
        devices.append({
            "mac": mac,
            "name": info["name"] or fallback_name,
            "paired": info["paired"],
            "trusted": info["trusted"],
            "connected": info["connected"],
            "icon": info["icon"],
            "audio": info["audio"],
        })
    # Enceintes audio d'abord, puis appareils connectes, puis ordre alpha.
    devices.sort(key=lambda d: (not d["audio"], not d["connected"], d["name"].lower()))
    return devices


async def start_scan(seconds: int = 20, on_tick=None):
    """Lance une decouverte temporisee. `on_tick` (coroutine sans arg) est appelee
    ~toutes les 3 s pour rafraichir la liste cote UI. Bloque jusqu'a la fin."""
    global _scan_proc
    if _op_lock.locked():
        # une operation (appairage/connexion) est en cours -> pas de decouverte
        # concurrente (elle perturberait l'echange A2DP).
        logger.info("[BLUETOOTH] scan ignore (operation en cours)")
        return
    if is_scanning():
        # un scan tourne deja -> ne pas reassigner _scan_proc (clobbererait la
        # comptabilite du scan en cours).
        logger.info("[BLUETOOTH] scan ignore (deja en cours)")
        return
    await power_on()
    await stop_scan()
    # On detient _op_lock UNIQUEMENT pendant la creation du subprocess pour qu'il
    # ne demarre pas dans la fenetre entre le stop_scan et l'acquisition du lock
    # par pair()/connect() (sinon le scan perturberait l'echange A2DP). On le
    # relache aussitot : le scan reste tuable par leur stop_scan, on ne bloque
    # donc pas pair/connect 20 s.
    try:
        await asyncio.wait_for(_op_lock.acquire(), timeout=0.001)
    except asyncio.TimeoutError:
        logger.info("[BLUETOOTH] scan ignore (operation en cours)")
        return
    try:
        my_proc = await asyncio.create_subprocess_exec(
            "bluetoothctl", "--timeout", str(seconds), "scan", "on",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception as e:
        logger.error("[BLUETOOTH] scan impossible: %s", e)
        # ne pas toucher _scan_proc : un owner concurrent pourrait l'avoir reaffecte.
        return
    finally:
        _op_lock.release()
    _scan_proc = my_proc
    logger.info("[BLUETOOTH] scan demarre (%ss)", seconds)
    elapsed = 0
    # On keye toute la boucle sur my_proc (local) : si un autre start_scan reassigne
    # _scan_proc, on ne lui vole pas sa comptabilite.
    while _scan_proc is my_proc and my_proc.returncode is None and elapsed < seconds:
        await asyncio.sleep(3)
        elapsed += 3
        if on_tick:
            try:
                await on_tick()
            except Exception:
                pass
    try:
        await my_proc.wait()
    except Exception:
        pass
    if _scan_proc is my_proc:
        _scan_proc = None
    logger.info("[BLUETOOTH] scan termine")


async def stop_scan():
    """Coupe la decouverte en cours."""
    global _scan_proc
    if is_scanning():
        try:
            _scan_proc.kill()
        except Exception:
            pass
    _scan_proc = None
    await _run(["scan", "off"], timeout=5)


async def pair(mac: str) -> tuple[bool, str]:
    """Appairage robuste (recette validee sur JBL Xtreme 4) :
    1) on purge tout bond perime via `remove` — sinon une cle de liaison desynchro
       fait echouer chaque retentative en AuthenticationFailed ;
    2) UNE session bluetoothctl a agent persistant (pairable on + agent maintenus)
       fait pair -> trust -> connect d'un seul tenant ;
    3) on verifie l'etat REEL (info) au lieu de croire la sortie texte."""
    async with _op_lock:
        # stop_scan() DANS le lock : sans ca, un scan pourrait redemarrer dans la
        # fenetre entre le stop et l'acquisition du lock et perturber l'echange A2DP.
        await stop_scan()  # interrompt toute decouverte UI -> libere le radio
        await _run(["remove", mac], timeout=8)
        out = await _session([
            ("power on", 0.5),
            ("pairable on", 0.5),
            ("agent NoInputNoOutput", 0.5),
            ("default-agent", 0.5),
            ("scan on", 6),
            (f"pair {mac}", 10),
            (f"trust {mac}", 1),
            (f"connect {mac}", 6),
            ("scan off", 0.3),
        ], overall_timeout=40)
    low = out.lower()
    _, info_out = await _run(["info", mac], timeout=5)
    info = _parse_info(info_out)
    if info["connected"] or info["paired"]:
        logger.info("[BLUETOOTH] appaire %s (connected=%s)", mac, info["connected"])
        return True, ""
    if "authenticationfailed" in low.replace(" ", "").replace("'", ""):
        err = "appairage refuse — remets l'enceinte en mode appairage"
    elif "not available" in low or "not ready" in low:
        err = "enceinte introuvable — allume-la et rapproche-la"
    else:
        err = "echec appairage"
    logger.warning("[BLUETOOTH] echec pair %s: %s", mac, err)
    return False, err


async def connect(mac: str, attempts: int = 4) -> tuple[bool, str]:
    """Reconnecte un appareil deja appaire (bond existant). Serialise, avec
    RE-ESSAIS : une enceinte qui sort de veille ne presente pas toujours son
    profil A2DP au 1er essai (-> br-connection-profile-unavailable / in-progress) ;
    elle l'accepte a la 2e-3e tentative apres un court delai."""
    async with _op_lock:
        # stop_scan() DANS le lock (cf. pair) : evite qu'un scan redemarre dans la
        # fenetre stop -> acquisition et perturbe la (re)connexion A2DP.
        await stop_scan()
        await _run(["trust", mac], timeout=5)
        last = ""
        for i in range(attempts):
            rc, out = await _run(["connect", mac], timeout=20)
            low = out.lower()
            if rc == 0 and ("successful" in low or "already" in low):
                logger.info("[BLUETOOTH] connecte %s (essai %d)", mac, i + 1)
                return True, ""
            last = _last_line(out) or "echec connexion"
            if i < attempts - 1:
                await asyncio.sleep(3)
    logger.warning("[BLUETOOTH] echec connect %s apres %d essais: %s", mac, attempts, last)
    return False, last


async def disconnect(mac: str) -> tuple[bool, str]:
    async with _op_lock:
        rc, out = await _run(["disconnect", mac], timeout=15)
    low = out.lower()
    ok = rc == 0 and ("successful" in low or "not connected" in low)
    return ok, "" if ok else (_last_line(out) or "echec")


async def forget(mac: str) -> tuple[bool, str]:
    async with _op_lock:
        rc, out = await _run(["remove", mac], timeout=10)
    low = out.lower()
    ok = rc == 0 and ("removed" in low or "not available" in low)
    return ok, "" if ok else (_last_line(out) or "echec")
