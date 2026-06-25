"""Guided LiveKit wakeword training jobs for the admin panel."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import secrets
import shutil
import sys
import wave
import zipfile
from array import array
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
WAKEWORD_JOBS_DIR = BACKEND_DIR / "audio" / "wakeword_jobs"
WAKEWORD_MODELS_DIR = BACKEND_DIR / "audio" / "models"
LIVEKIT_V2_MODEL = WAKEWORD_MODELS_DIR / "terminator_livekit_v2.onnx"

SAMPLE_RATE = 16000
SAMPLE_KINDS = ("positive", "background", "negative")
_JOB_RE = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-f0-9]{6}$")
_WAKEWORD_RE = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_job_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _validate_kind(kind: str) -> str:
    if kind not in SAMPLE_KINDS:
        raise ValueError("Type d'echantillon invalide")
    return kind


def _manifest_path(job_id: str) -> Path:
    return job_dir(job_id) / "manifest.json"


def job_dir(job_id: str) -> Path:
    """Return a job directory after strict id validation."""
    if not _JOB_RE.fullmatch(str(job_id)):
        raise ValueError("Job wakeword invalide")
    root = WAKEWORD_JOBS_DIR.resolve()
    target = (root / job_id).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Chemin job invalide")
    return target


def sample_path(job_id: str, kind: str, filename: str) -> Path:
    """Return a sample path after strict containment checks."""
    _validate_kind(kind)
    if not _FILENAME_RE.fullmatch(filename) or not filename.endswith(".wav"):
        raise ValueError("Nom de fichier invalide")
    root = (job_dir(job_id) / "samples" / kind).resolve()
    target = (root / filename).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Chemin sample invalide")
    return target


def create_job(wakeword: str = "terminator") -> dict:
    if not _WAKEWORD_RE.fullmatch(wakeword):
        raise ValueError("Mot-reveil invalide")
    job_id = _new_job_id()
    base = job_dir(job_id)
    for kind in SAMPLE_KINDS:
        (base / "samples" / kind).mkdir(parents=True, exist_ok=True)
    (base / "exports").mkdir(parents=True, exist_ok=True)
    (base / "uploads").mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "id": job_id,
        "wakeword": wakeword,
        "status": "recording",
        "created_at": _now(),
        "updated_at": _now(),
        "samples": {kind: [] for kind in SAMPLE_KINDS},
        "package": None,
        "upload": None,
        "installed": None,
    }
    save_job(manifest)
    return manifest


def save_job(manifest: dict) -> None:
    manifest["updated_at"] = _now()
    _atomic_write_json(_manifest_path(manifest["id"]), manifest)


def load_job(job_id: str) -> dict:
    path = _manifest_path(job_id)
    if not path.exists():
        raise FileNotFoundError("Job wakeword introuvable")
    return json.loads(path.read_text(encoding="utf-8"))


def list_jobs() -> list[dict]:
    if not WAKEWORD_JOBS_DIR.exists():
        return []
    jobs = []
    for path in sorted(WAKEWORD_JOBS_DIR.iterdir(), reverse=True):
        if path.is_dir() and _JOB_RE.fullmatch(path.name):
            try:
                jobs.append(load_job(path.name))
            except Exception as exc:
                logger.warning("[WAKEWORD-JOBS] Manifest ignore %s: %s", path, exc)
    return jobs


def analyze_pcm16(pcm: bytes, sample_rate: int = SAMPLE_RATE, kind: str = "positive") -> dict:
    _validate_kind(kind)
    if not pcm:
        raise ValueError("Audio vide")
    if len(pcm) % 2:
        pcm = pcm[:-1]
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise ValueError("Audio vide")

    peak = max(abs(int(v)) for v in samples)
    rms = int(math.sqrt(sum(int(v) * int(v) for v in samples) / len(samples)))
    duration_s = round(len(samples) / sample_rate, 2)
    if kind == "background":
        good = duration_s >= 1.0 and peak < 30000
    else:
        good = duration_s >= 0.5 and rms >= 500 and peak >= 900
    return {
        "rms": rms,
        "peak": peak,
        "max": peak,
        "duration_s": duration_s,
        "good": good,
        "sample_rate": sample_rate,
    }


def save_sample(job_id: str, kind: str, pcm: bytes, label: str = "", sample_rate: int = SAMPLE_RATE) -> dict:
    kind = _validate_kind(kind)
    manifest = load_job(job_id)
    metrics = analyze_pcm16(pcm, sample_rate=sample_rate, kind=kind)
    sample_index = len(manifest["samples"].get(kind, [])) + 1
    stamp = datetime.now().strftime("%H%M%S")
    filename = f"{kind}_{sample_index:03d}_{stamp}.wav"
    out = job_dir(job_id) / "samples" / kind / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)

    sample = {
        "file": filename,
        "kind": kind,
        "label": str(label or "")[:80],
        "created_at": _now(),
        **metrics,
    }
    manifest.setdefault("samples", {}).setdefault(kind, []).append(sample)
    manifest["status"] = "recording"
    save_job(manifest)
    return sample


def delete_sample(job_id: str, kind: str, filename: str) -> bool:
    path = sample_path(job_id, kind, filename)
    deleted = False
    if path.exists():
        path.unlink()
        deleted = True
    manifest = load_job(job_id)
    manifest["samples"][kind] = [
        sample for sample in manifest["samples"].get(kind, [])
        if sample.get("file") != filename
    ]
    save_job(manifest)
    return deleted


def build_training_pack(job_id: str, base_url: str = "") -> Path:
    manifest = load_job(job_id)
    base = job_dir(job_id)
    exports = base / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    pack = exports / f"piboard_wakeword_training_{job_id}.zip"

    package_manifest = dict(manifest)
    package_manifest["downloaded_from"] = base_url
    package_manifest["notes"] = {
        "positive": "Reference clips from the real room/user; keep for validation and future fine-tuning.",
        "background": "Use as local background/adversarial material during LiveKit training.",
        "negative": "Similar phrases that should not trigger the wakeword.",
    }

    with zipfile.ZipFile(pack, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(package_manifest, indent=2, ensure_ascii=False) + "\n")
        zf.writestr("README_TRAINING.md", _training_readme(manifest, base_url))
        zf.writestr("configs/terminator_v2.yaml", _training_yaml(manifest))
        script = _training_script()
        info = zipfile.ZipInfo("train.command")
        info.external_attr = 0o755 << 16
        zf.writestr(info, script)
        for kind in SAMPLE_KINDS:
            for sample in manifest["samples"].get(kind, []):
                src = base / "samples" / kind / sample["file"]
                if src.exists():
                    zf.write(src, f"samples/{kind}/{sample['file']}")

    manifest["status"] = "packaged"
    manifest["package"] = {
        "file": pack.name,
        "created_at": _now(),
        "download_url": f"{base_url.rstrip('/')}/admin/api/wakeword/jobs/{job_id}/download" if base_url else "",
    }
    save_job(manifest)
    return pack


def package_path(job_id: str) -> Path:
    manifest = load_job(job_id)
    package = manifest.get("package") or {}
    filename = package.get("file")
    if not filename or not _FILENAME_RE.fullmatch(filename):
        raise FileNotFoundError("Pack entrainement absent")
    path = job_dir(job_id) / "exports" / filename
    if not path.exists():
        raise FileNotFoundError("Pack entrainement absent")
    return path


def save_uploaded_model(job_id: str, filename: str, data: bytes) -> Path:
    if not filename.endswith(".onnx"):
        raise ValueError("Le fichier doit etre un .onnx")
    target = job_dir(job_id) / "uploads" / "terminator_livekit_v2.onnx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    validated = validate_uploaded_model(target)
    manifest = load_job(job_id)
    manifest["status"] = "uploaded"
    manifest["upload"] = {
        "file": validated.name,
        "size": validated.stat().st_size,
        "created_at": _now(),
    }
    save_job(manifest)
    return validated


def validate_uploaded_model(path: Path, allow_minimal_proto: bool = False) -> Path:
    path = Path(path)
    if path.suffix != ".onnx":
        raise ValueError("Le fichier doit etre un .onnx")
    if not path.exists():
        raise ValueError("Fichier ONNX introuvable")
    size = path.stat().st_size
    if size < 8:
        raise ValueError("Fichier ONNX trop petit")
    if size > 80 * 1024 * 1024:
        raise ValueError("Fichier ONNX trop volumineux")

    errors = []
    try:
        import onnx  # type: ignore

        model = onnx.load(str(path))
        onnx.checker.check_model(model)
        return path
    except ImportError as exc:
        errors.append(f"onnx indisponible: {exc}")
    except Exception as exc:
        errors.append(f"onnx checker: {exc}")

    try:
        from livekit.wakeword import WakeWordModel  # type: ignore

        WakeWordModel(models=[str(path)])
        return path
    except ImportError as exc:
        errors.append(f"livekit-wakeword indisponible: {exc}")
    except Exception as exc:
        errors.append(f"livekit-wakeword: {exc}")

    data = path.read_bytes()[:4096]
    if allow_minimal_proto and data.startswith(b"\x08") and b"onnx" in data:
        return path
    raise ValueError("Modele ONNX invalide (" + " ; ".join(errors) + ")")


def install_model(job_id: str, source: Path | None = None, activate: bool = False) -> dict:
    manifest = load_job(job_id)
    if source is None:
        source = job_dir(job_id) / "uploads" / "terminator_livekit_v2.onnx"
    source = Path(source)
    if not source.exists() or source.suffix != ".onnx":
        raise FileNotFoundError("Modele ONNX uploade introuvable")

    WAKEWORD_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LIVEKIT_V2_MODEL.with_suffix(".onnx.tmp")
    shutil.copyfile(source, tmp)
    os.replace(tmp, LIVEKIT_V2_MODEL)

    if activate:
        activate_livekit_v2()

    manifest["status"] = "installed"
    manifest["installed"] = {
        "path": str(LIVEKIT_V2_MODEL),
        "size": LIVEKIT_V2_MODEL.stat().st_size,
        "activated": bool(activate),
        "created_at": _now(),
    }
    save_job(manifest)
    return {
        "ok": True,
        "model": "terminator_v2",
        "path": str(LIVEKIT_V2_MODEL),
        "activated": bool(activate),
    }


def activate_livekit_v2() -> None:
    from admin.config_manager import config

    config.set("wakeword", "engine", "livekit")
    config.set("wakeword", "name", "terminator")
    config.set("wakeword", "livekit_model", "terminator_v2")


def model_status() -> dict:
    try:
        from admin.config_manager import config
        active = config.get("wakeword", "livekit_model", "terminator_v1")
    except Exception:
        active = "terminator_v1"
    return {
        "active": active,
        "v1_exists": (WAKEWORD_MODELS_DIR / "terminator_livekit.onnx").exists(),
        "v2_exists": LIVEKIT_V2_MODEL.exists(),
        "v2_path": str(LIVEKIT_V2_MODEL),
        "v2_size": LIVEKIT_V2_MODEL.stat().st_size if LIVEKIT_V2_MODEL.exists() else 0,
    }


def _training_yaml(manifest: dict) -> str:
    negatives = [
        "terminer",
        "terminal",
        "terminus",
        "determinateur",
        "exterminateur",
        "generateur",
        "ordinateur",
        "allume la lumiere",
        "mets la musique",
        "arrete la musique",
    ]
    for sample in manifest["samples"].get("negative", []):
        label = str(sample.get("label") or "").strip()
        if label and label not in negatives:
            negatives.append(label)
    rendered_negatives = "\n".join(f'  - "{item}"' for item in negatives)
    return f"""# Generated by PI-Board for LiveKit wakeword V2.
model_name: terminator_v2
target_phrases: ["{manifest.get("wakeword", "terminator")}"]

n_samples: 8000
n_samples_val: 1500
n_background_samples: 800
n_background_samples_val: 200
tts_batch_size: 50

custom_negative_phrases:
{rendered_negatives}

noise_scales: [0.98]
noise_scale_ws: [0.98]
length_scales: [0.75, 1.0, 1.25]
slerp_weights: [0.2, 0.35, 0.5, 0.65, 0.8]

data_dir: ./data
output_dir: ./output_terminator_v2

augmentation:
  clip_duration: 2.0
  batch_size: 16
  rounds: 3
  background_paths: [./data/backgrounds, ./samples/background]
  rir_paths: [./data/rirs]

model:
  model_type: conv_attention
  model_size: small

steps: 30000
learning_rate: 0.0001
weight_decay: 0.01
label_smoothing: 0.05
max_negative_weight: 3000
target_fp_per_hour: 0.5

batch_n_per_class:
  positive: 50
  adversarial_negative: 50
  ACAV100M_sample: 1024
  background_noise: 50
"""


def _training_script() -> str:
    return """#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
echo "PI-Board wakeword training pack"
echo "This runs on the Mac, not on the Raspberry Pi."

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install it from https://www.python.org/downloads/macos/"
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "livekit-wakeword>=0.2.1"

mkdir -p data/backgrounds/pi_room
cp samples/background/*.wav data/backgrounds/pi_room/ 2>/dev/null || true

echo
echo "Starting LiveKit wakeword pipeline. This can take a long time."
echo
livekit-wakeword setup -c configs/terminator_v2.yaml --skip-acav
livekit-wakeword run configs/terminator_v2.yaml

MODEL="$(find output_terminator_v2 -name '*.onnx' | head -n 1)"
if [ -z "$MODEL" ]; then
  echo "No ONNX model found in output_terminator_v2"
  exit 1
fi

cp "$MODEL" terminator_livekit_v2.onnx
echo
echo "Done: $(pwd)/terminator_livekit_v2.onnx"
echo "Upload this file back to the PI-Board admin page."
"""


def _training_readme(manifest: dict, base_url: str) -> str:
    counts = {kind: len(manifest["samples"].get(kind, [])) for kind in SAMPLE_KINDS}
    upload_url = f"{base_url.rstrip('/')}/admin/" if base_url else "la meme page admin du PI-Board"
    return f"""# PI-Board Wakeword Training

Ce pack prepare le modele LiveKit V2 pour le mot-reveil `{manifest.get("wakeword", "terminator")}`.

## Contenu

- Positifs: {counts["positive"]} clips reels du mot-reveil.
- Bruit de fond: {counts["background"]} clips de la piece.
- Negatifs: {counts["negative"]} clips ou libelles proches qui ne doivent pas declencher.

## Sur le Mac

1. Dezippez ce dossier.
2. Double-cliquez `train.command`.
3. Acceptez l'ouverture si macOS demande confirmation.
4. Laissez l'entrainement finir.
5. Recupererez `terminator_livekit_v2.onnx` dans ce dossier.

Si le double-clic ne lance pas le script, ouvrez Terminal dans ce dossier et lancez:

```bash
chmod +x train.command
./train.command
```

## Retour vers le Pi

Ouvrez {upload_url}, revenez sur `Configurer le Wakeword`, puis uploadez
`terminator_livekit_v2.onnx`.

Le Pi validera le fichier avant de l'installer. Le modele V1 reste disponible
comme rollback.
"""
