import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

numpy = types.ModuleType("numpy")
numpy.int16 = "int16"
sys.modules.setdefault("numpy", numpy)

eff_word_net = types.ModuleType("eff_word_net")
eff_word_net_engine = types.ModuleType("eff_word_net.engine")
eff_word_net_audio = types.ModuleType("eff_word_net.audio_processing")
eff_word_net_engine.HotwordDetector = object
eff_word_net_audio.Resnet50_Arc_loss = object
sys.modules.setdefault("eff_word_net", eff_word_net)
sys.modules.setdefault("eff_word_net.engine", eff_word_net_engine)
sys.modules.setdefault("eff_word_net.audio_processing", eff_word_net_audio)

livekit = types.ModuleType("livekit")
livekit_wakeword = types.ModuleType("livekit.wakeword")
livekit_wakeword.WakeWordModel = object
sys.modules.setdefault("livekit", livekit)
sys.modules.setdefault("livekit.wakeword", livekit_wakeword)

openwakeword = types.ModuleType("openwakeword")
openwakeword_model = types.ModuleType("openwakeword.model")
openwakeword_model.Model = object
sys.modules.setdefault("openwakeword", openwakeword)
sys.modules.setdefault("openwakeword.model", openwakeword_model)

from audio import wakeword


class LiveKitModelResolutionTest(unittest.TestCase):
    def test_resolve_livekit_model_v1_returns_existing_v1(self):
        key, path = wakeword.resolve_livekit_model("terminator_v1")

        self.assertEqual(key, "terminator_v1")
        self.assertEqual(path, wakeword.LKWW_MODEL)
        self.assertEqual(Path(path).name, "terminator_livekit.onnx")

    def test_resolve_livekit_model_v2_falls_back_to_v1_when_missing(self):
        original = dict(wakeword.LKWW_MODELS)
        self.addCleanup(lambda: wakeword.LKWW_MODELS.clear())
        self.addCleanup(lambda: wakeword.LKWW_MODELS.update(original))
        wakeword.LKWW_MODELS["terminator_v2"] = str(
            Path(wakeword.MODELS_DIR) / "definitely_missing_v2.onnx"
        )

        key, path = wakeword.resolve_livekit_model("terminator_v2")

        self.assertEqual(key, "terminator_v1")
        self.assertEqual(path, wakeword.LKWW_MODEL)

    def test_resolve_livekit_model_unknown_falls_back_to_v1(self):
        key, path = wakeword.resolve_livekit_model("unknown")

        self.assertEqual(key, "terminator_v1")
        self.assertEqual(path, wakeword.LKWW_MODEL)


if __name__ == "__main__":
    unittest.main()
