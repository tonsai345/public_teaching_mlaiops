"""Lab 2 — prove the registered model can be reloaded by version, from the registry.

    python scripts/reload_check.py --name itcs355-6688063 --version 1

This is the lab's quiet test. Models that cannot be reloaded six months later are the
commonest form of dead work in industry, and the cause is nearly always a serialization
assumption: a custom class that no longer exists, a library version that moved, a
preprocessing step that only ever lived in a notebook.

Loading from a local file instead of the registry defeats the purpose and is checked.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, data


AZURE_SUBSCRIPTION_ID = "ce0c4612-4e67-4c7b-b2e6-0a2198ad93b3"
AZURE_RESOURCE_GROUP = "itcs355-6688063-rg"
AZURE_WORKSPACE = "itcs355-workspace"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="registered model name")
    ap.add_argument("--version", required=True)
    ap.add_argument("--rows", type=int, default=5)
    args = ap.parse_args()

    from azure.ai.ml import MLClient
    from azure.identity import DefaultAzureCredential

    ml_client = MLClient(
        DefaultAzureCredential(),
        AZURE_SUBSCRIPTION_ID,
        AZURE_RESOURCE_GROUP,
        AZURE_WORKSPACE,
    )

    print(f"downloading {args.name}:{args.version} from registry")
    download_path = Path("reports/_reload")
    download_path.mkdir(parents=True, exist_ok=True)

    ml_client.models.download(
        name=args.name,
        version=args.version,
        download_path=str(download_path),
    )

    # Azure ML downloads a directory containing the model file
    model_files = list(download_path.rglob("*.joblib"))
    if not model_files:
        print("ERROR: no .joblib file found in downloaded model")
        return 1
    model_file = model_files[0]
    print(f"model file: {model_file}")

    import joblib
    model = joblib.load(model_file)

    cfg = config.load(strict=False)
    df = data.load_raw(cfg.raw_path)
    _, _, test_df = data.split(df, seed=20260101)
    sample = test_df[data.FEATURES].head(args.rows)

    predictions = model.predict(sample)
    probabilities = model.predict_proba(sample)[:, 1]

    print(f"\nScored {args.rows} rows from the test set:")
    for i, (pred, prob) in enumerate(zip(predictions, probabilities)):
        print(f"  row {i+1}: prediction={pred}  probability={prob:.4f}")

    print("\nReload check PASSED — model loaded from the registry and scored rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
