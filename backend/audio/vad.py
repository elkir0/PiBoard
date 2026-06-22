"""Silero VAD (ONNX, sans torch) — detection de parole pour l'endpointing du STT
streaming. Le modele est celui livre avec openWakeWord (silero_vad.onnx), ou une
copie dans backend/audio/models/. Frame de 512 echantillons (32 ms @ 16 kHz)."""
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

try:
    import onnxruntime as ort
    HAS_ORT = True
except ImportError:  # pragma: no cover
    HAS_ORT = False

FRAME = 512  # echantillons par frame VAD (32 ms @ 16 kHz)

_HERE = os.path.dirname(__file__)


def _find_model() -> str | None:
    local = os.path.join(_HERE, "models", "silero_vad.onnx")
    if os.path.exists(local):
        return local
    try:
        import openwakeword
        p = os.path.join(os.path.dirname(openwakeword.__file__),
                         "resources", "models", "silero_vad.onnx")
        if os.path.exists(p):
            return p
    except Exception:
        pass
    return None


class SileroVAD:
    """Probabilite de parole [0..1] par frame de 512 echantillons int16 (16 kHz).

    Mode degrade : si onnxruntime/modele absent, available()==False et prob()==1.0
    (on considere tout comme parole -> le STT streaming se comporte alors comme
    une capture a duree fixe, jamais de crash)."""

    def __init__(self):
        self._sess = None
        path = _find_model()
        if HAS_ORT and path:
            try:
                so = ort.SessionOptions()
                so.inter_op_num_threads = 1
                so.intra_op_num_threads = 1
                self._sess = ort.InferenceSession(
                    path, sess_options=so, providers=["CPUExecutionProvider"])
                logger.info("[VAD] Silero charge (%s)", path)
            except Exception as e:
                logger.error("[VAD] Erreur chargement: %s", e)
        else:
            logger.warning("[VAD] indisponible (onnxruntime ou modele manquant)")
        self.reset()

    def available(self) -> bool:
        return self._sess is not None

    def reset(self):
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)

    def prob(self, frame_i16: np.ndarray) -> float:
        if self._sess is None:
            return 1.0
        x = (frame_i16.astype(np.float32) / 32768.0).reshape(1, -1)
        try:
            out, hn, cn = self._sess.run(
                None,
                {"input": x, "sr": np.array(16000, dtype=np.int64),
                 "h": self._h, "c": self._c},
            )
            self._h, self._c = hn, cn
            return float(out[0][0])
        except Exception as e:
            logger.warning("[VAD] prob err: %s", e)
            return 1.0
