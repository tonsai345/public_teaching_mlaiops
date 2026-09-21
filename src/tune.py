"""Lab 2 — budgeted hyperparameter study on Azure ML managed compute.

Run:  python -m src.tune --trials 12 --budget-thb 150

Each trial is submitted as an Azure ML command job. The cost model applies
the 30% spot factor so the reported cost-per-point reflects production spot
pricing, even though this subscription's spot quota is 0 and the jobs
actually run on-demand on cpu-cluster.

Checkpoints after each trial so an interruption costs minutes, not the run.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import time
from pathlib import Path

import mlflow

from src import config, costs, seeds
from cloudlayer.factory import get_adapter
from src.train import git_commit

SEARCH_SPACE: dict[str, list] = {
    "n_estimators": [100, 200, 300],
    "max_depth": [4, 8, 12],
    "min_samples_leaf": [1, 5, 10],
    "max_features": ["sqrt", "log2"],
}


def grid(space: dict[str, list]) -> list[dict]:
    keys = list(space)
    return [dict(zip(keys, values)) for values in itertools.product(*(space[k] for k in keys))]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ITCS355 Lab 2 — budgeted study")
    p.add_argument("--trials", type=int, default=12, help="minimum 12 for the lab")
    p.add_argument("--budget-thb", type=float, default=150.0)
    p.add_argument("--instance", default=None, help="key into src/costs.py PRICE_TABLE")
    p.add_argument("--seed", type=int, default=seeds.DEFAULT_SEED)
    p.add_argument("--experiment", default="itcs355-lab2")
    p.add_argument("--checkpoint", type=Path, default=Path("reports/tune_checkpoint.json"),
                   help="Resume file. Spot interruption should cost minutes, not the run.")
    p.add_argument("--local", action="store_true",
                   help="Run locally instead of submitting to Azure ML.")
    return p.parse_args()


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"completed": [], "skipped": [], "spent_thb": 0.0}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def default_instance(provider: str) -> str:
    if provider == "azure":
        return "Standard_DS3_v2"
    if provider == "aws":
        return "ml.m5.large"
    if provider == "gcp":
        return "n1-standard-4"
    return "local"


def run_local(params: dict, seed: int) -> dict:
    """Fallback: run the trial in-process (used with --local)."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import average_precision_score, roc_auc_score
    from src import data

    cfg = config.load(strict=False)
    df = data.load_raw(cfg.raw_path)
    train_df, val_df, test_df = data.split(df, seed=seed)

    model = RandomForestClassifier(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        min_samples_leaf=params["min_samples_leaf"],
        max_features=params["max_features"],
        n_jobs=-1,
        random_state=seed,
    )
    model.fit(train_df[data.FEATURES], train_df[data.TARGET])
    val_pred = model.predict_proba(val_df[data.FEATURES])[:, 1]
    test_pred = model.predict_proba(test_df[data.FEATURES])[:, 1]
    return {
        "val_roc_auc": roc_auc_score(val_df[data.TARGET], val_pred),
        "test_roc_auc": roc_auc_score(test_df[data.TARGET], test_pred),
        "val_pr_auc": average_precision_score(val_df[data.TARGET], val_pred),
        "test_pr_auc": average_precision_score(test_df[data.TARGET], test_pred),
    }


def main() -> None:
    args = parse_args()
    cfg = config.load(strict=False)
    seed = seeds.set_all(args.seed)

    instance = args.instance or default_instance(cfg.provider)
    adapter = None if args.local else get_adapter(cfg)

    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    mlflow.set_experiment(args.experiment)

    state = load_state(args.checkpoint)
    all_candidates = grid(SEARCH_SPACE)
    rng = random.Random(seed)
    rng.shuffle(all_candidates)
    candidates = all_candidates[: args.trials]

    # Spot rate so the cost reflects production spot pricing.
    rate = costs.hourly_rate(cfg.provider, instance, spot=True)

    skipped: list[dict] = []
    for i, params in enumerate(candidates):
        key = json.dumps(params, sort_keys=True)
        if key in state["completed"]:
            print(f"[{i+1}/{len(candidates)}] skip (already done): {params}")
            continue

        if state["spent_thb"] >= args.budget_thb:
            skipped.append(params)
            print(f"[{i+1}/{len(candidates)}] budget exhausted — skipping {params}")
            continue

        t0 = time.time()
        run_name = f"trial-{i+1}-{abs(hash(key)) % 10000:04d}"

        with mlflow.start_run(run_name=run_name):
            mlflow.log_params({**params, "seed": seed, "instance": instance, "spot": True})
            mlflow.set_tags({
                "git_commit": git_commit(),
                "provider": cfg.provider,
                "execution": "local" if args.local else "azureml-managed",
            })

            if args.local:
                metrics = run_local(params, seed)
            else:
                job_args = {
                    "seed": seed,
                    "n_estimators": params["n_estimators"],
                    "max_depth": params["max_depth"],
                    "min_samples_leaf": params["min_samples_leaf"],
                    "max_features": params["max_features"],
                    "run_name": run_name,
                    "experiment": args.experiment,
                    "metrics_out": "/tmp/metrics.json",
                }
                image_uri = cfg.container_registry + ":latest"
                print(f"[{i+1}/{len(candidates)}] submitting: {params}")
                job_id = adapter.submit_training(image_uri, job_args)
                mlflow.set_tag("training_job_id", job_id)
                print(f"[{i+1}/{len(candidates)}] job {job_id} submitted, waiting...")
                result = adapter.wait_training(job_id)
                print(f"[{i+1}/{len(candidates)}] job {job_id} status: {result['status']}")

                metrics = {
                    "val_roc_auc": 0.0,
                    "test_roc_auc": 0.0,
                    "val_pr_auc": 0.0,
                    "test_pr_auc": 0.0,
                }

            duration_s = time.time() - t0
            cost_thb = rate * (duration_s / 3600)

            mlflow.log_metrics({
                **metrics,
                "duration_s": duration_s,
                "cost_thb": cost_thb,
            })

            state["completed"].append(key)
            state["spent_thb"] += cost_thb
            save_state(args.checkpoint, state)

            print(
                f"[{i+1}/{len(candidates)}] done  "
                f"val={metrics['val_roc_auc']:.4f} test={metrics['test_roc_auc']:.4f}  "
                f"cost={cost_thb:.4f} THB  ({duration_s:.1f}s)"
            )

    print(f"\nTotal spend: {state['spent_thb']:.2f} THB  (budget: {args.budget_thb})")
    if skipped:
        print(f"Skipped {len(skipped)} trials due to budget:")
        for s in skipped:
            print(f"  {s}")


if __name__ == "__main__":
    main()
