"""Lab 5 — register the model produced by the `train` step, with lineage.

Called by the pipeline's `register` step, only when `gate_decision == 'pass'`.
Does NOT retrain: reads /inputs/model/model.joblib and /inputs/metrics/metrics.json.

    python scripts/register.py --model-dir /inputs/model --metrics /inputs/metrics/metrics.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from cloudlayer.factory import get_adapter


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"],
                             check=True, capture_output=True, text=True)
        return out.stdout.strip()[:12]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, required=True)
    ap.add_argument("--metrics", type=Path, required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--stage", default="Staging")
    args = ap.parse_args()

    cfg = config.load(strict=False)
    model_name = args.name or cfg.model_registry_name

    model_file = args.model_dir / "model.joblib"
    if not model_file.exists():
        raise SystemExit(f"model.joblib missing under {args.model_dir}")

    payload = json.loads(args.metrics.read_text())
    lineage = {
        "git_commit": git_commit(),
        "data_version": str(payload.get("data_fingerprint", "unknown")),
        "metrics_fingerprint": fingerprint(args.metrics),
        "mlflow_run_id": os.environ.get("AZUREML_RUN_ID", "n/a"),
        "training_job_id": os.environ.get("AZUREML_ROOT_RUN_ID", "n/a"),
        "image_digest": os.environ.get("AZUREML_IMAGE_DIGEST", "n/a"),
        "seed": str(payload.get("seed", "unknown")),
        "metric_val": f"{float(payload.get('val_roc_auc', 0.0)):.4f}",
        "metric_test": f"{float(payload.get('test_roc_auc', 0.0)):.4f}",
    }

    adapter = get_adapter(cfg)
    version = adapter.register_model(
        str(args.model_dir), model_name, lineage=lineage, stage=args.stage
    )
    print(f"registered {model_name} version {version}")
    for k, v in lineage.items():
        print(f"  {k} = {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
