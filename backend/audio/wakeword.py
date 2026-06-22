import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# Try to import EfficientWord-Net (preferred)
try:
    from eff_word_net.engine import HotwordDetector
    from eff_word_net.audio_processing import Resnet50_Arc_loss
    HAS_EWN = True
except ImportError:
    HAS_EWN = False
    logger.warning("[WAKEWORD] EfficientWord-Net non disponible")

# Preferred (V3): livekit-wakeword — conv-attention head, ~60x moins de faux
# declenchements qu'openWakeWord, CPU/offline, tourne sur le Pi aarch64.
try:
    from livekit.wakeword import WakeWordModel as LKWWModel
    HAS_LKWW = True
except ImportError:
    HAS_LKWW = False
    logger.warning("[WAKEWORD] livekit-wakeword non disponible")

# Fallback: openWakeWord
try:
    from openwakeword.model import Model as OWWModel
    HAS_OWW = True
except ImportError:
    HAS_OWW = False

# Admin config (runtime settings)
try:
    from admin.config_manager import config as admin_config
except ImportError:
    admin_config = None

def _cfg(key, default):
    """Read from admin config, fallback to default."""
    if admin_config:
        return admin_config.get("wakeword", key, default)
    return default

# Defaults (overridden by admin config at runtime)
COOLDOWN_S_DEFAULT = 15.0
# Seuil au repos. Mesure terrain (.152) : faux declenchements ambiants jusqu'a ~0.46,
# vrais "terminator" >=0.51 -> 0.48 separe proprement (0.42 laissait passer du bruit).
THRESHOLD_DEFAULT = 0.48  # quiet room : pics reels ~0.5-0.7, bruit ambiant <0.46
# Quand le Pi joue de l'audio (musique/TTS), le micro le capte (pas d'AEC avec
# le Devialet) et le modele score haut sur la musique -> on durcit le seuil.
MUSIC_THRESHOLD_BOOST = 0.17  # seuil effectif ~0.65 pendant la musique (0.48 + 0.17)

# EfficientWord-Net paths
REFS_DIR = os.path.join(os.path.dirname(__file__), "hotword_refs")
WAKEWORD_NAME = "terminator"
WAKEWORD_REF = os.path.join(REFS_DIR, f"{WAKEWORD_NAME}_ref.json")

# openWakeWord fallback
OWW_CHUNK_SIZE = 1280
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
CUSTOM_MODEL = os.path.join(MODELS_DIR, "Terminator!.onnx")

# Mot-réveil choisi (config.wakeword.name) -> modèle openWakeWord.
# « terminator » = modèle custom entraîné (fichier .onnx) ; les autres = modèles de
# base livrés avec openWakeWord (résolus par nom court). Seul openWakeWord sait
# changer de mot : livekit ne connaît QUE « terminator » (son modèle est entraîné dessus).
OWW_WORD_MODELS = {
    "terminator": CUSTOM_MODEL,
    "hey_jarvis": "hey_jarvis",
    "hey_mycroft": "hey_mycroft",
    "alexa": "alexa",
}

# livekit-wakeword (preferre). predict() veut un chunk d'environ 2 s a 16 kHz
# (il calcule mel + embeddings sur toute la fenetre, fonction pure). On garde
# donc une fenetre glissante de 2 s et on l'evalue toutes les ~0.4 s.
LKWW_MODEL = os.path.join(MODELS_DIR, "terminator_livekit.onnx")
LKWW_WINDOW = 32000   # 2.0 s @ 16 kHz
LKWW_HOP = 6400       # ~0.4 s entre deux predictions

# EWN expects 24000 samples (1.5 seconds at 16kHz)
EWN_FRAME_SIZE = 24000


class WakeWordDetector:
    def __init__(self, on_wake: Callable[[], Awaitable[None]] | None = None):
        self.on_wake = on_wake
        self._detector = None
        self._last_trigger = 0.0
        self._debug_counter = 0
        self.running = False
        self.paused = False
        # Callback optionnel renvoyant True quand le Pi joue de l'audio
        # (musique/TTS) -> on applique MUSIC_THRESHOLD_BOOST au seuil.
        self.busy_check: Callable[[], bool] | None = None
        self._needs_reset = False
        self._use_ewn = False
        # livekit-wakeword state (preferre)
        self._lkww_model = None
        self._use_lkww = False
        self._lkww_buffer = np.array([], dtype=np.int16)
        self._lkww_since_pred = 0
        # openWakeWord fallback state
        self._oww_model = None
        self._buffer = np.array([], dtype=np.int16)

    async def start(self):
        # Read config from admin panel (live values)
        # config.json corrompue (valeur non numerique) ne doit pas empecher le
        # boot du detecteur -> repli sur les defauts.
        try:
            self._threshold = float(_cfg("threshold", THRESHOLD_DEFAULT))
        except (TypeError, ValueError):
            logger.warning("[WAKEWORD] threshold invalide -> defaut %.2f", THRESHOLD_DEFAULT)
            self._threshold = float(THRESHOLD_DEFAULT)
        try:
            self._cooldown = float(_cfg("cooldown_s", COOLDOWN_S_DEFAULT))
        except (TypeError, ValueError):
            self._cooldown = float(COOLDOWN_S_DEFAULT)
        engine_pref = _cfg("engine", "livekit")
        word = _cfg("name", WAKEWORD_NAME)  # mot-réveil choisi (terminator/hey_jarvis/…)

        # 1) livekit-wakeword (prefere) : meilleur detecteur, mais NE connait que
        #    « terminator » (modele entraine). On l'utilise donc seulement si le mot
        #    demande est terminator ET le moteur n'est pas force sur openWakeWord.
        #    Sinon -> openWakeWord (seul a pouvoir changer de mot).
        if engine_pref != "oww" and word == "terminator" and HAS_LKWW and os.path.exists(LKWW_MODEL):
            try:
                self._lkww_model = LKWWModel(models=[LKWW_MODEL])
                self._use_lkww = True
                logger.info("[WAKEWORD] livekit-wakeword charge (%s, threshold=%.2f, cooldown=%.0fs)",
                           os.path.basename(LKWW_MODEL), self._threshold, self._cooldown)
            except Exception as e:
                logger.error("[WAKEWORD] Erreur init livekit-wakeword: %s", e)
                self._use_lkww = False

        if not self._use_lkww and engine_pref == "ewn" and HAS_EWN and os.path.exists(WAKEWORD_REF):
            try:
                base_model = Resnet50_Arc_loss()
                self._detector = HotwordDetector(
                    hotword=WAKEWORD_NAME,
                    model=base_model,
                    reference_file=WAKEWORD_REF,
                    threshold=self._threshold,
                    relaxation_time=2,
                    continuous=True,
                )
                self._use_ewn = True
                logger.info("[WAKEWORD] EfficientWord-Net charge (%s, threshold=%.2f, cooldown=%.0fs)",
                           WAKEWORD_NAME, self._threshold, self._cooldown)
            except Exception as e:
                logger.error("[WAKEWORD] Erreur init EfficientWord-Net: %s", e)
                self._use_ewn = False

        if not self._use_ewn and not self._use_lkww:
            if HAS_OWW:
                # Mot choisi -> modèle openWakeWord. « terminator » = custom (fichier) ;
                # un fichier custom manquant ou un nom inconnu retombe sur hey_jarvis.
                oww_model = OWW_WORD_MODELS.get(word, CUSTOM_MODEL)
                if isinstance(oww_model, str) and oww_model.endswith(".onnx") and not os.path.exists(oww_model):
                    logger.warning("[WAKEWORD] modele custom absent (%s) -> hey_jarvis", oww_model)
                    oww_model = "hey_jarvis"
                try:
                    self._oww_model = OWWModel(wakeword_models=[oww_model], inference_framework="onnx")
                    logger.info("[WAKEWORD] openWakeWord (mot=%s, modele=%s, threshold=%.2f, cooldown=%.0fs)",
                               word, os.path.basename(str(oww_model)), self._threshold, self._cooldown)
                except Exception as e:
                    logger.error("[WAKEWORD] init openWakeWord (%s) echec: %s -> hey_jarvis", oww_model, e)
                    self._oww_model = OWWModel(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            else:
                logger.info("[WAKEWORD] Mode mock actif")

        self.running = True

    async def process(self, audio_queue: asyncio.Queue):
        if self._use_lkww:
            await self._process_lkww(audio_queue)
        elif self._use_ewn:
            await self._process_ewn(audio_queue)
        else:
            await self._process_oww(audio_queue)

    async def _process_ewn(self, audio_queue: asyncio.Queue):
        """Process audio with EfficientWord-Net detector.

        Key optimizations vs naive approach:
        - scoreFrame runs in executor (doesn't block asyncio event loop)
        - Full frame slide (1.5s) instead of half (0.75s) = 2x fewer inferences
        - Small sleep after each inference to yield CPU to PipeWire/AirPlay
        """
        buffer = np.array([], dtype=np.int16)
        loop = asyncio.get_event_loop()
        # Single-thread pool — prevents EWN from eating all CPU cores
        ewn_pool = ThreadPoolExecutor(max_workers=1)

        while self.running:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if self.paused:
                buffer = np.array([], dtype=np.int16)
                self._needs_reset = True
                continue

            if self._needs_reset:
                self._needs_reset = False
                buffer = np.array([], dtype=np.int16)
                continue

            buffer = np.concatenate([buffer, chunk])

            # Process ONE frame at a time, skip excess buffer to save CPU
            if len(buffer) >= EWN_FRAME_SIZE:
                # If buffer is way too full, skip to latest frame (drop old audio)
                if len(buffer) > EWN_FRAME_SIZE * 3:
                    buffer = buffer[-(EWN_FRAME_SIZE):]

                frame = buffer[:EWN_FRAME_SIZE]
                buffer = buffer[EWN_FRAME_SIZE:]

                rms = int(np.sqrt(np.mean(frame.astype(np.float32)**2)))

                try:
                    # Run inference in thread pool — don't block event loop
                    result = await loop.run_in_executor(
                        ewn_pool, lambda f=frame: self._detector.scoreFrame(f, unsafe=True)
                    )

                    self._debug_counter += 1
                    if result is not None:
                        confidence = result.get("confidence", 0)
                        matched = result.get("match", False)
                        if self._debug_counter % 10 == 0 or confidence > 0.3:
                            logger.info("[WAKEWORD] %s conf=%.3f match=%s (rms=%d)",
                                       WAKEWORD_NAME, confidence, matched, rms)

                        if matched:
                            now = time.monotonic()
                            if now - self._last_trigger < self._cooldown:
                                pass
                            else:
                                self._last_trigger = now
                                logger.info("[WAKEWORD] Detecte! (EWN conf=%.2f)", confidence)
                                if self.on_wake:
                                    await self.on_wake()
                    else:
                        if self._debug_counter % 25 == 0:
                            logger.info("[WAKEWORD] %s (silence, rms=%d)", WAKEWORD_NAME, rms)

                    # Long pause after inference — 500ms gives CPU ~40% instead of ~95%
                    await asyncio.sleep(0.5)

                except Exception as e:
                    if self._debug_counter % 100 == 0:
                        logger.warning("[WAKEWORD] EWN error: %s", e)

    def _effective_threshold(self) -> float:
        """Seuil de declenchement, durci quand le Pi joue de l'audio (le micro
        capte la musique/TTS et le modele score haut dessus)."""
        if self.busy_check is not None:
            try:
                if self.busy_check():
                    return self._threshold + MUSIC_THRESHOLD_BOOST
            except Exception:
                pass
        return self._threshold

    async def _process_lkww(self, audio_queue: asyncio.Queue):
        """livekit-wakeword : fenetre glissante de 2 s, predict toutes les ~0.4 s.

        predict() est une fonction pure (mel + embeddings sur toute la fenetre) et
        synchrone (onnxruntime) -> run_in_executor pour ne pas bloquer la loop.
        """
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if not self._lkww_model:
                continue
            if self.paused:
                self._lkww_buffer = np.array([], dtype=np.int16)
                self._lkww_since_pred = 0
                continue

            # Accumule et garde les 2 dernieres secondes.
            self._lkww_buffer = np.concatenate([self._lkww_buffer, chunk])
            if len(self._lkww_buffer) > LKWW_WINDOW:
                self._lkww_buffer = self._lkww_buffer[-LKWW_WINDOW:]
            self._lkww_since_pred += len(chunk)

            # On evalue seulement avec assez de contexte et au plus ~toutes les 0.4 s.
            if len(self._lkww_buffer) < LKWW_WINDOW or self._lkww_since_pred < LKWW_HOP:
                continue
            self._lkww_since_pred = 0

            try:
                scores = await loop.run_in_executor(
                    None, self._lkww_model.predict, self._lkww_buffer.copy())
            except Exception as e:
                logger.warning("[WAKEWORD] livekit predict err: %s", e)
                continue
            if not scores:
                continue

            name, score = max(scores.items(), key=lambda kv: kv[1])
            effective = self._effective_threshold()
            self._debug_counter += 1
            if self._debug_counter % 25 == 0 or score > 0.02:
                logger.info("[WAKEWORD] lkww %s score=%.3f (seuil=%.2f)", name, score, effective)

            if score >= effective:
                now = time.monotonic()
                if now - self._last_trigger < self._cooldown:
                    continue
                self._last_trigger = now
                self._lkww_buffer = np.array([], dtype=np.int16)  # evite un double trigger
                logger.info("[WAKEWORD] Detecte! (livekit %s score=%.2f)", name, score)
                if self.on_wake:
                    await self.on_wake()

    async def _process_oww(self, audio_queue: asyncio.Queue):
        """Fallback: process audio with openWakeWord."""
        while self.running:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if not self._oww_model:
                continue

            if self.paused:
                self._buffer = np.array([], dtype=np.int16)
                self._needs_reset = True
                continue

            if self._needs_reset:
                self._needs_reset = False
                self._buffer = np.array([], dtype=np.int16)
                silence = np.zeros(OWW_CHUNK_SIZE * 10, dtype=np.int16)
                for i in range(10):
                    self._oww_model.predict(silence[i*OWW_CHUNK_SIZE:(i+1)*OWW_CHUNK_SIZE])
                logger.info("[WAKEWORD] Model flushed after pause")
                continue

            self._buffer = np.concatenate([self._buffer, chunk])

            while len(self._buffer) >= OWW_CHUNK_SIZE:
                frame = self._buffer[:OWW_CHUNK_SIZE]
                self._buffer = self._buffer[OWW_CHUNK_SIZE:]

                try:
                    prediction = self._oww_model.predict(frame)

                    for model_name, score in prediction.items():
                        self._debug_counter += 1
                        if self._debug_counter % 25 == 0 or score > 0.02:
                            logger.info("[WAKEWORD] %s score=%.3f (rms=%d)", model_name, score,
                                       np.sqrt(np.mean(frame.astype(np.float32)**2)))

                        if score >= self._threshold:
                            now = time.monotonic()
                            if now - self._last_trigger < self._cooldown:
                                continue
                            self._last_trigger = now
                            logger.info("[WAKEWORD] Detecte! (score=%.2f)", score)
                            if self.on_wake:
                                await self.on_wake()
                except Exception as e:
                    if self._debug_counter % 100 == 0:
                        logger.warning("[WAKEWORD] oww error: %s", e)

    def reset_cooldown(self):
        """Reset cooldown timer."""
        self._last_trigger = time.monotonic()
        logger.info("[WAKEWORD] Cooldown reset")

    async def stop(self):
        self.running = False
        logger.info("[WAKEWORD] Arrete")
