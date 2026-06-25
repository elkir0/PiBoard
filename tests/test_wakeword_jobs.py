import importlib
import json
import shutil
import sys
import tempfile
import unittest
import wave
import zipfile
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def make_pcm16(duration_s=1.0, sample_rate=16000, amp=1200):
    count = int(duration_s * sample_rate)
    samples = array("h", [amp if i % 2 == 0 else -amp for i in range(count)])
    return samples.tobytes()


class WakewordJobsTest(unittest.TestCase):
    def setUp(self):
        try:
            self.jobs = importlib.import_module("admin.wakeword_jobs")
        except ModuleNotFoundError:
            self.jobs = None
            return

        self.tmp = Path(tempfile.mkdtemp(prefix="piboard-wakeword-jobs-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

        self.original_jobs_dir = self.jobs.WAKEWORD_JOBS_DIR
        self.original_models_dir = self.jobs.WAKEWORD_MODELS_DIR
        self.jobs.WAKEWORD_JOBS_DIR = self.tmp / "jobs"
        self.jobs.WAKEWORD_MODELS_DIR = self.tmp / "models"
        self.jobs.LIVEKIT_V2_MODEL = self.jobs.WAKEWORD_MODELS_DIR / "terminator_livekit_v2.onnx"
        self.fake_config = {}
        self.jobs.activate_livekit_v2 = lambda: self.fake_config.update({"livekit_model": "terminator_v2"})
        self.addCleanup(self._restore_paths)

    def _restore_paths(self):
        if self.jobs is None:
            return
        self.jobs.WAKEWORD_JOBS_DIR = self.original_jobs_dir
        self.jobs.WAKEWORD_MODELS_DIR = self.original_models_dir
        self.jobs.LIVEKIT_V2_MODEL = self.original_models_dir / "terminator_livekit_v2.onnx"

    def require_jobs_module(self):
        self.assertIsNotNone(self.jobs, "admin.wakeword_jobs module must exist")
        return self.jobs

    def test_creates_job_manifest_with_safe_id(self):
        jobs = self.require_jobs_module()

        job = jobs.create_job("terminator")

        self.assertRegex(job["id"], r"^[0-9]{8}_[0-9]{6}_[a-f0-9]{6}$")
        self.assertEqual(job["wakeword"], "terminator")
        self.assertEqual(job["status"], "recording")
        manifest_path = jobs.job_dir(job["id"]) / "manifest.json"
        self.assertTrue(manifest_path.exists())
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["samples"]["positive"], [])

    def test_rejects_path_traversal_job_ids(self):
        jobs = self.require_jobs_module()

        with self.assertRaises(ValueError):
            jobs.job_dir("../bad")

    def test_saves_recorded_sample_and_updates_manifest(self):
        jobs = self.require_jobs_module()
        job = jobs.create_job("terminator")

        sample = jobs.save_sample(
            job["id"],
            "positive",
            make_pcm16(duration_s=1.0, amp=1500),
            label="proche",
        )

        self.assertEqual(sample["kind"], "positive")
        self.assertTrue(sample["good"])
        self.assertGreater(sample["rms"], 500)
        wav_path = jobs.job_dir(job["id"]) / "samples" / "positive" / sample["file"]
        self.assertTrue(wav_path.exists())
        with wave.open(str(wav_path), "rb") as wf:
            self.assertEqual(wf.getframerate(), 16000)
            self.assertEqual(wf.getnchannels(), 1)
        reloaded = jobs.load_job(job["id"])
        self.assertEqual(len(reloaded["samples"]["positive"]), 1)

    def test_builds_training_pack_with_manifest_readme_config_script_and_samples(self):
        jobs = self.require_jobs_module()
        job = jobs.create_job("terminator")
        jobs.save_sample(job["id"], "positive", make_pcm16(), label="normal")
        jobs.save_sample(job["id"], "background", make_pcm16(amp=200), label="salon")
        jobs.save_sample(job["id"], "negative", make_pcm16(amp=800), label="terminal")

        pack = jobs.build_training_pack(job["id"], "http://piboard.local:8000")

        self.assertTrue(pack.exists())
        with zipfile.ZipFile(pack) as zf:
            names = set(zf.namelist())
        self.assertIn("manifest.json", names)
        self.assertIn("README_TRAINING.md", names)
        self.assertIn("train.command", names)
        self.assertIn("configs/terminator_v2.yaml", names)
        self.assertTrue(any(name.startswith("samples/positive/") for name in names))
        self.assertTrue(any(name.startswith("samples/background/") for name in names))
        self.assertTrue(any(name.startswith("samples/negative/") for name in names))

    def test_uploaded_model_must_be_valid_onnx_or_obvious_wakeword_model(self):
        jobs = self.require_jobs_module()
        job = jobs.create_job("terminator")
        bad_path = jobs.job_dir(job["id"]) / "uploads" / "bad.onnx"
        bad_path.parent.mkdir(parents=True, exist_ok=True)
        bad_path.write_bytes(b"not an onnx")

        with self.assertRaises(ValueError):
            jobs.validate_uploaded_model(bad_path)

        model_path = jobs.job_dir(job["id"]) / "uploads" / "terminator_livekit_v2.onnx"
        model_path.write_bytes(b"\x08\x09\x12\x04onnx")
        validated = jobs.validate_uploaded_model(model_path, allow_minimal_proto=True)
        self.assertEqual(validated.name, "terminator_livekit_v2.onnx")

    def test_install_model_copies_uploaded_candidate_and_can_activate_v2(self):
        jobs = self.require_jobs_module()
        job = jobs.create_job("terminator")
        upload_dir = jobs.job_dir(job["id"]) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        candidate = upload_dir / "terminator_livekit_v2.onnx"
        candidate.write_bytes(b"\x08\x09\x12\x04onnx")

        installed = jobs.install_model(job["id"], candidate, activate=True)

        self.assertEqual(installed["model"], "terminator_v2")
        self.assertTrue(jobs.LIVEKIT_V2_MODEL.exists())
        self.assertEqual(jobs.LIVEKIT_V2_MODEL.read_bytes(), b"\x08\x09\x12\x04onnx")
        reloaded = jobs.load_job(job["id"])
        self.assertEqual(reloaded["status"], "installed")


if __name__ == "__main__":
    unittest.main()
