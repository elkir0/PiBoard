import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from admin import routes
from admin import wakeword_jobs


class WakewordRoutesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="piboard-wakeword-routes-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

        self.original_jobs_dir = wakeword_jobs.WAKEWORD_JOBS_DIR
        self.original_models_dir = wakeword_jobs.WAKEWORD_MODELS_DIR
        wakeword_jobs.WAKEWORD_JOBS_DIR = self.tmp / "jobs"
        wakeword_jobs.WAKEWORD_MODELS_DIR = self.tmp / "models"
        wakeword_jobs.LIVEKIT_V2_MODEL = (
            wakeword_jobs.WAKEWORD_MODELS_DIR / "terminator_livekit_v2.onnx"
        )
        self.addCleanup(self._restore_paths)

        app = FastAPI()
        app.dependency_overrides[routes.require_auth] = lambda: "test"
        app.include_router(routes.admin_router)
        self.client = TestClient(app)

    def _restore_paths(self):
        wakeword_jobs.WAKEWORD_JOBS_DIR = self.original_jobs_dir
        wakeword_jobs.WAKEWORD_MODELS_DIR = self.original_models_dir
        wakeword_jobs.LIVEKIT_V2_MODEL = self.original_models_dir / "terminator_livekit_v2.onnx"

    def test_create_job_and_model_status_routes(self):
        created = self.client.post("/admin/api/wakeword/jobs", json={"wakeword": "terminator"})
        self.assertEqual(created.status_code, 200)
        job = created.json()
        self.assertEqual(job["wakeword"], "terminator")

        status = self.client.get("/admin/api/wakeword/model-status")
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["v2_exists"])

    def test_package_route_returns_download_url(self):
        created = self.client.post("/admin/api/wakeword/jobs", json={"wakeword": "terminator"})
        self.assertEqual(created.status_code, 200)
        job_id = created.json()["id"]
        wakeword_jobs.save_sample(job_id, "positive", b"\xe8\x03\x18\xfc" * 8000)

        packaged = self.client.post(f"/admin/api/wakeword/jobs/{job_id}/package")

        self.assertEqual(packaged.status_code, 200)
        data = packaged.json()
        self.assertTrue(data["download_url"].endswith(f"/admin/api/wakeword/jobs/{job_id}/download"))
        self.assertTrue((wakeword_jobs.job_dir(job_id) / "exports").exists())


if __name__ == "__main__":
    unittest.main()
