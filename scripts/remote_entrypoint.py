"""Bootstrap for Azure ML managed jobs.

Runs inside the training container. Downloads raw data from BLOB_URI,
trains, and uploads artifacts back to BLOB_URI.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from azure.storage.blob import BlobServiceClient


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=20260101)
    p.add_argument("--n-estimators", type=int, default=100)
    p.add_argument("--max-depth", type=int, default=6)
    p.add_argument("--min-samples-leaf", type=int, default=5)
    p.add_argument("--max-features", default="sqrt",
                   help="Features per split: 'sqrt', 'log2', or a float")
    p.add_argument("--run-name", default=None)
    p.add_argument("--experiment", default="itcs355-lab2")
    p.add_argument("--metrics-out", default="/tmp/metrics.json")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    blob_uri = os.environ.get("BLOB_URI")
    if not conn_str or not blob_uri:
        sys.exit("AZURE_STORAGE_CONNECTION_STRING and BLOB_URI must be set")

    # Parse BLOB_URI: https://account.blob.core.windows.net/container
    rest = blob_uri.replace("https://", "")
    parts = rest.split("/")
    account_name = parts[0].split(".")[0]
    container_name = parts[1]

    client = BlobServiceClient.from_connection_string(conn_str)
    container_client = client.get_container_client(container_name)

    # --- 1. Download raw data ---
    local_data_dir = Path("/app/data/raw")
    local_data_dir.mkdir(parents=True, exist_ok=True)
    local_csv = local_data_dir / "sensors.csv"

    blob_name = "raw/sensors.csv"
    print(f"[bootstrap] downloading {blob_name} from {container_name}")
    with open(local_csv, "wb") as f:
        data = container_client.download_blob(blob_name).readall()
        f.write(data)
    print(f"[bootstrap] downloaded {len(data)} bytes")

    # --- 2. Train ---
    cmd = [
        "python", "-m", "src.train",
        "--seed", str(args.seed),
        "--n-estimators", str(args.n_estimators),
        "--max-depth", str(args.max_depth),
        "--min-samples-leaf", str(args.min_samples_leaf),
        "--max-features", str(args.max_features),
        "--experiment", args.experiment,
        "--metrics-out", args.metrics_out,
    ]
    if args.run_name:
        cmd += ["--run-name", args.run_name]
    print(f"[bootstrap] running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    # --- 3. Upload artifacts ---
    print("[bootstrap] uploading artifacts")
    with open(args.metrics_out, "rb") as f:
        container_client.upload_blob(
            f"runs/{args.run_name or 'latest'}/metrics.json",
            f,
            overwrite=True,
        )
    print("[bootstrap] done")


if __name__ == "__main__":
    main()
