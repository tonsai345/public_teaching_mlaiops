"""ITCS355 Lab 1 — reproducible training.

Deterministic given a seed. Reads data from cfg.raw_path (local path
or, in Lab 2, a path downloaded from BLOB_URI by the bootstrap script).
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import mlflow
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from src import config, data, seeds


def git_commit() -> str:
    """Return the current Git commit SHA, or 'unknown' if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
        return result.stdout.strip()[:12]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ITCS355 Lab 1 — reproducible training")
    p.add_argument("--n-estimators", type=int, default=200)
    p.add_argument("--max-depth", type=int, default=8)
    p.add_argument("--min-samples-leaf", type=int, default=5)
    p.add_argument("--max-features", default="sqrt",
                   help="Features per split: 'sqrt', 'log2', or a float")
    p.add_argument("--seed", type=int, default=seeds.DEFAULT_SEED)
    p.add_argument("--experiment", default="itcs355-lab1")
    p.add_argument("--run-name", default=None)
    p.add_argument("--metrics-out", type=Path, default=None,
                   help="Write final metrics as JSON. Used by `make verify`.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = config.load(strict=False)
    seed = seeds.set_all(args.seed)

    df = data.load_raw(cfg.raw_path)
    fingerprint = data.data_fingerprint(cfg.raw_path)
    train_df, val_df, test_df = data.split(df, seed=seed)

    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    mlflow.set_experiment(args.experiment)

    with mlflow.start_run(run_name=args.run_name):
        mlflow.log_params({
            "n_estimators": args.n_estimators,
            "max_depth": args.max_depth,
            "min_samples_leaf": args.min_samples_leaf,
            "max_features": args.max_features,
            "seed": seed,
            "n_features": len(data.FEATURES),
        })
        mlflow.set_tags({
            "git_commit": git_commit(),
            "data_fingerprint": fingerprint,
            "split_strategy": "group_by_machine_id",
            "n_train_rows": len(train_df),
            "n_val_rows": len(val_df),
            "n_test_rows": len(test_df),
        })

        model = RandomForestClassifier(
            n_estimators=args.n_estimators,
            max_depth=args.max_depth,
            min_samples_leaf=args.min_samples_leaf,
            max_features=args.max_features,
            n_jobs=-1,
            random_state=seed,
        )
        model.fit(train_df[data.FEATURES], train_df[data.TARGET])

        metrics: dict[str, float] = {}
        for name, part in (("val", val_df), ("test", test_df)):
            proba = model.predict_proba(part[data.FEATURES])[:, 1]
            metrics[f"{name}_roc_auc"] = float(roc_auc_score(part[data.TARGET], proba))
            metrics[f"{name}_pr_auc"] = float(average_precision_score(part[data.TARGET], proba))
        mlflow.log_metrics(metrics)

        # skops 0.15 refuses to serialise sklearn tree models unless the caller names
        # the types it trusts. sklearn.tree._tree.Tree stores raw node indices that
        # scikit-learn indexes without bounds checking, so a malicious file can segfault
        # the process on .predict(). We built this model in this process from our own
        # data, so trusting it here is a statement about provenance, not a bypass — and
        # it is scoped to the one type rather than everything skops reports.
        mlflow.sklearn.log_model(
            model, artifact_path="model",
            skops_trusted_types=["sklearn.tree._tree.Tree"],
        )

        out_metrics = {
            "seed": seed,
            "data_fingerprint": fingerprint,
            "val_roc_auc": metrics["val_roc_auc"],
            "val_pr_auc": metrics["val_pr_auc"],
            "test_roc_auc": metrics["test_roc_auc"],
            "test_pr_auc": metrics["test_pr_auc"],
        }
        if args.metrics_out:
            args.metrics_out = Path(args.metrics_out)
            args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
            args.metrics_out.write_text(json.dumps(out_metrics, indent=2))
        print(json.dumps(out_metrics, indent=2))


if __name__ == "__main__":
    main()
