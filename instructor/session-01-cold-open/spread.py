"""Run the peer notebook's logic N times and show what it actually produces.

    python instructor/session-01-cold-open/spread.py --runs 10

For the Session 1 debrief. Put it on screen after the pairs report their numbers: the
notebook claims 0.965, and ten honest runs of the same code land somewhere else every
time. Then the last two columns show why the number was never 0.965 to begin with.

Needs pandas, scikit-learn and numpy. It does not import the notebook — it reimplements
the same cells, so it stays runnable when nbformat is not installed.
"""
from __future__ import annotations

import argparse
import statistics

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

FEATURES = ["temp_c", "vibration_mm_s", "pressure_kpa",
            "hours_since_service", "load_pct", "ambient_humidity"]
CLAIM = 0.965


def build_dataset() -> pd.DataFrame:
    """Exactly the notebook's data cell — including the unseeded generator."""
    rng = np.random.default_rng()
    rows = []
    for m in range(240):
        base_temp = rng.normal(72, 9)
        base_vib = rng.normal(3.0, 1.1)
        wear = rng.uniform(0, 6000)
        risk = 1 / (1 + np.exp(-((base_temp - 72) / 9 * 1.1
                                 + (base_vib - 3) / 1.1 * 0.9
                                 + wear / 6000 * 1.2 - 2.6)))
        failed = int(rng.random() < risk)
        for r in range(25):
            rows.append({
                "machine_id": f"M-{m:03d}",
                "temp_c": base_temp + rng.normal(0, 1.5),
                "vibration_mm_s": base_vib + rng.normal(0, 0.25),
                "pressure_kpa": rng.normal(310, 24),
                "hours_since_service": wear + r * 8,
                "load_pct": rng.normal(66, 12),
                "ambient_humidity": rng.normal(55, 9),
                "failed_within_7d": failed,
            })
    return pd.DataFrame(rows)


def forest() -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=300, max_depth=12, min_samples_leaf=2)


def one_run() -> tuple[float, float]:
    df = build_dataset()
    X, y = df[FEATURES], df["failed_within_7d"]

    # The notebook's split: row-wise, so readings from one machine land on both sides.
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25)
    leaky = roc_auc_score(y_te, forest().fit(X_tr, y_tr).predict_proba(X_te)[:, 1])

    # The honest split: grouped, so a machine is wholly in train or wholly in test.
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.25).split(X, y, groups=df["machine_id"]))
    honest = roc_auc_score(y.iloc[te],
                           forest().fit(X.iloc[tr], y.iloc[tr]).predict_proba(X.iloc[te])[:, 1])
    return leaky, honest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=10)
    args = ap.parse_args()

    print(f"The notebook claims test ROC AUC = {CLAIM}\n")
    print(f"  {'run':<5}{'as written':>12}{'grouped split':>16}")
    leaky, honest = [], []
    for i in range(1, args.runs + 1):
        a, b = one_run()
        leaky.append(a)
        honest.append(b)
        print(f"  {i:<5}{a:>12.3f}{b:>16.3f}")

    print(f"\n  {'mean':<5}{statistics.mean(leaky):>12.3f}{statistics.mean(honest):>16.3f}")
    print(f"  {'range':<5}{max(leaky) - min(leaky):>12.3f}{max(honest) - min(honest):>16.3f}")
    print(f"\n  Nobody reproduced {CLAIM}: "
          f"{sum(abs(a - CLAIM) < 0.001 for a in leaky)}/{args.runs} runs hit it exactly.")
    print(f"  Leakage was worth {statistics.mean(leaky) - statistics.mean(honest):+.3f} AUC — "
          "the claim was inflated before it was unstable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
