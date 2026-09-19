"""Register the chosen Lab 2 model in Azure ML, with full lineage.

Run:  python scripts/register_model.py --name itcs355-6688063
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import mlflow
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

from src import config, data, seeds
from src.train import git_commit
from cloudlayer.factory import get_adapter


AZURE_SUBSCRIPTION_ID = "ce0c4612-4e67-4c7b-b2e6-0a2198ad93b3"
AZURE_RESOURCE_GROUP = "itcs355-6688063-rg"
AZURE_WORKSPACE = "itcs355-workspace"


CHOSEN = {
    "n_estimators": 300,
    "max_depth": 4,
    "min_samples_leaf": 10,
    "max_features": "log2",
}


def resolve_image_digest() -> str:
    """Read the most recent digest for the itcs355 repository in ACR."""
    try:
        result = subprocess.run(
            ["az", "acr", "repository", "show-manifests",
             "--name", "itcs3556688063acr",
             "--repository", "itcs355",
             "--orderby", "time_desc",
             "--query", "[0].digest",
             "-o", "tsv"],
            check=True, capture_output=True, text=True,
        )
        return result.stdout.strip() or "unknown"
    except subprocess.CalledProcessError:
        return "unknown"


def resolve_last_job_id() -> str:
    """Return the most recent Lab 2 training job name from Azure ML."""
    try:
        result = subprocess.run(
            ["az", "ml", "job", "list",
             "--workspace-name", AZURE_WORKSPACE,
             "--resource-group", AZURE_RESOURCE_GROUP,
             "--query", "[?display_name=='lab2-train-remote'] | [0].name",
             "-o", "tsv"],
            check=True, capture_output=True, text=True,
        )
        return result.stdout.strip() or "n/a"
    except subprocess.CalledProcessError:
        return "n/a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="registered model name")
    ap.add_argument("--stage", default="Staging")
    ap.add_argument("--seed", type=int, default=seeds.DEFAULT_SEED)
    args = ap.parse_args()

    cfg = config.load(strict=False)
    seed = seeds.set_all(args.seed)

    df = data.load_raw(cfg.raw_path)
    fingerprint = data.data_fingerprint(cfg.raw_path)
    train_df, val_df, test_df = data.split(df, seed=seed)

    model = RandomForestClassifier(
        n_estimators=CHOSEN["n_estimators"],
        max_depth=CHOSEN["max_depth"],
        min_samples_leaf=CHOSEN["min_samples_leaf"],
        max_features=CHOSEN["max_features"],
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(train_df[data.FEATURES], train_df[data.TARGET])

    val_pred = model.predict_proba(val_df[data.FEATURES])[:, 1]
    test_pred = model.predict_proba(test_df[data.FEATURES])[:, 1]
    val_roc = roc_auc_score(val_df[data.TARGET], val_pred)
    test_roc = roc_auc_score(test_df[data.TARGET], test_pred)

    out = Path("reports/model.joblib")
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out)
    print(f"wrote {out}")

    image_digest = resolve_image_digest()
    training_job_id = resolve_last_job_id()

    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    mlflow.set_experiment("itcs355-lab2-registry")

    with mlflow.start_run(run_name=f"register-{args.name}") as run:
        mlflow.log_params(CHOSEN)
        mlflow.log_params({"seed": seed, "stage": args.stage})
        mlflow.log_metrics({
            "val_roc_auc": val_roc,
            "test_roc_auc": test_roc,
        })
        mlflow.set_tags({
            "git_commit": git_commit(),
            "data_version": fingerprint,
            "training_job_id": training_job_id,
            "image_digest": image_digest,
        })

        lineage = {
            "git_commit": git_commit(),
            "data_version": fingerprint,
            "mlflow_run_id": run.info.run_id,
            "training_job_id": training_job_id,
            "image_digest": image_digest,
            "seed": str(seed),
            "metric_val": f"{val_roc:.4f}",
            "metric_test": f"{test_roc:.4f}",
        }

        adapter = get_adapter(cfg)
        version = adapter.register_model(str(out), args.name, lineage=lineage, stage=args.stage)
        mlflow.set_tag("registered_version", version)

    print(f"registered {args.name} version {version} (stage={args.stage})")
    print("lineage:")
    for k, v in lineage.items():
        print(f"  {k} = {v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
