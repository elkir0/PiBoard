import asyncio
import logging
import numpy as np

logger = logging.getLogger(__name__)

TARGET_RATE = 16000
CHANNELS = 1
CHUNK_SAMPLES = 1024  # samples per chunk at TARGET_RATE
CAPTURE_RATE = 48000  # native mic rate, resampled to TARGET_RATE


def resample(data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return data
    # Simple decimation: 48000 -> 16000 = factor 3
    # Much lighter than scipy.signal.resample_poly on Pi 4
    ratio = src_rate // dst_rate
    if src_rate % dst_rate == 0 and ratio > 1:
        return data[::ratio].copy()
    # Fallback: linear interpolation
    length = int(len(data) * dst_rate / src_rate)
    indices = np.linspace(0, len(data) - 1, length)
    return np.interp(indices, np.arange(len(data)), data.astype(np.float32)).astype(np.int16)


class AudioCapture:
    def __init__(self, device_name: str = "AI-Voice"):
        self.device_name = device_name
        # Device ALSA explicite (RESPEAKER_DEVICE). Vide = autodetection USB.
        try:
            from config import RESPEAKER_DEVICE
            self._explicit_device = (RESPEAKER_DEVICE or "").strip()
        except Exception:
            self._explicit_device = ""
        self.running = False
        self._process: asyncio.subprocess.Process | None = None
        self._listeners: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._listeners:
            self._listeners.remove(q)

    def _find_alsa_device(self) -> str | None:
        """Device ALSA du micro : RESPEAKER_DEVICE explicite si défini, sinon
        autodétection d'un micro USB via `arecord -l`."""
        if self._explicit_device:
            logger.info("[AUDIO] Micro explicite (RESPEAKER_DEVICE): %s", self._explicit_device)
            return self._explicit_device
        import subprocess
        try:
            result = subprocess.run(
                ["arecord", "-l"], capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.split("\n"):
                if self.device_name.lower() in line.lower() or "usb" in line.lower():
                    # Parse "card 3: AI-Voice [AI-Voice], device 0: USB Audio [USB Audio]"
                    parts = line.split(":")
                    if len(parts) >= 2:
                        card = parts[0].split()[-1]  # card number
                        logger.info("[AUDIO] Trouve: %s (card %s)", line.strip(), card)
                        return f"hw:{card},0"
        except Exception as e:
            logger.warning("[AUDIO] Erreur detection micro: %s", e)
        return None

    async def start(self):
        self.running = True

        # Retry finding mic up to 10 times (USB mic may not be ready at boot)
        for attempt in range(10):
            if not self.running:
                return
            device = self._find_alsa_device()
            if device:
                break

            if attempt < 9:
                wait = 5 if attempt < 5 else 10
                logger.info("[AUDIO] Micro non trouve, retry dans %ds (tentative %d/10)", wait, attempt + 1)
                await asyncio.sleep(wait)
        else:
            device = None

        # Boucle de supervision : tant que running, garder une capture vivante.
        # Si arecord meurt (USB debranche, xrun fatal, EOF), on re-detecte le
        # device et on relance ; sinon remplissage mock interruptible (re-teste
        # le device periodiquement) pour rendre le re-branchement USB recuperable.
        while self.running:
            if not device:
                device = self._find_alsa_device()

            if device:
                try:
                    await self._start_arecord(device)
                except Exception as e:
                    logger.warning("[AUDIO] Erreur ouverture %s: %s", device, e)
                if self.running:
                    logger.warning("[AUDIO] arecord mort, relance de la capture")
                device = None
            else:
                logger.warning("[AUDIO] Micro introuvable — mode mock (re-detection en cours)")
                await self._mock_loop()

            if self.running:
                await asyncio.sleep(2)

    async def _start_arecord(self, device: str):
        """Start arecord subprocess and read audio data."""
        # Compute bytes per chunk: we read at CAPTURE_RATE and resample to TARGET_RATE
        # Read bigger chunks at capture rate, then resample
        capture_chunk = CHUNK_SAMPLES * CAPTURE_RATE // TARGET_RATE  # 3072 samples at 48kHz
        bytes_per_read = capture_chunk * 2  # 16-bit = 2 bytes per sample

        self._process = await asyncio.create_subprocess_exec(
            "arecord",
            "-D", device,
            "-f", "S16_LE",
            "-r", str(CAPTURE_RATE),
            "-c", "1",
            "-t", "raw",
            "--buffer-size", str(capture_chunk * 4),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        logger.info("[AUDIO] Capture demarree via arecord (device=%s, rate=%d, resample=oui)", device, CAPTURE_RATE)

        try:
            while self.running and self._process.returncode is None:
                data = await self._process.stdout.read(bytes_per_read)
                if not data:
                    break

                # Lecture partielle du pipe peut renvoyer un nombre d'octets impair
                # (arecord tue en plein echantillon 16-bit) -> frombuffer exige un
                # multiple de 2. On drop au plus un demi-echantillon (inaudible).
                if len(data) % 2:
                    data = data[:-1]
                    if not data:
                        continue

                chunk = np.frombuffer(data, dtype=np.int16)
                # Resample 48kHz -> 16kHz
                chunk = resample(chunk, CAPTURE_RATE, TARGET_RATE)

                for q in self._listeners:
                    try:
                        q.put_nowait(chunk)
                    except asyncio.QueueFull:
                        pass
        except Exception as e:
            logger.error("[AUDIO] Erreur lecture: %s", e)
        finally:
            if self._process and self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    self._process.kill()
            logger.info("[AUDIO] arecord termine")

    async def _mock_loop(self):
        # Remplissage interruptible : pousse du silence pour garder les abonnes
        # vivants, mais retourne des qu'un micro reapparait (re-teste toutes
        # les ~3 s) pour que la supervision relance arecord.
        recheck_every = int(3.0 / (512 / TARGET_RATE))  # ~3 s en chunks
        i = 0
        while self.running:
            chunk = np.zeros(512, dtype=np.int16)
            for q in self._listeners:
                try:
                    q.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass
            await asyncio.sleep(512 / TARGET_RATE)
            i += 1
            if i >= recheck_every:
                i = 0
                if self._find_alsa_device():
                    logger.info("[AUDIO] Micro detecte — sortie du mode mock")
                    return

    async def stop(self):
        self.running = False
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._process.kill()
        logger.info("[AUDIO] Capture arretee")
