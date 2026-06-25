import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from admin.config_manager import DEFAULT_CONFIG
import runtime_config


class RuntimeConfigValidationTest(unittest.TestCase):
    def test_default_config_exposes_livekit_model(self):
        self.assertEqual(DEFAULT_CONFIG["wakeword"]["livekit_model"], "terminator_v1")

    def test_ws_config_allows_livekit_model_key(self):
        self.assertIn(("wakeword", "livekit_model"), runtime_config.ALLOWED_CONFIG_KEYS)

    def test_ws_config_accepts_known_livekit_models(self):
        coerce = runtime_config.CONFIG_COERCE[("wakeword", "livekit_model")]

        self.assertEqual(coerce("terminator_v1"), "terminator_v1")
        self.assertEqual(coerce("terminator_v2"), "terminator_v2")

    def test_ws_config_rejects_unknown_livekit_model(self):
        coerce = runtime_config.CONFIG_COERCE[("wakeword", "livekit_model")]

        with self.assertRaises(ValueError):
            coerce("bad_model")


if __name__ == "__main__":
    unittest.main()
