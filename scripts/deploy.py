"""Deploy the serving image to Container Apps and smoke-test it.

Run:  python scripts/deploy.py --model itcs355-6688063:2 --endpoint itcs355-serve
      python scripts/deploy.py --smoke-only --endpoint itcs355-serve
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from cloudlayer.factory import get_adapter


AZURE_RESOURCE_GROUP = "itcs355-6688063-rg"

SMOKE_PAYLOADS = [
    {"temp_c": 78.4, "vibration_mm_s": 3.1, "pressure_kpa": 315.2,
     "hours_since_service": 4200.0, "load_pct": 68.0, "ambient_humidity": 55.0},
    {"temp_c": 95.0, "vibration_mm_s": 8.2, "pressure_kpa": 420.0,
     "hours_since_service": 12000.0, "load_pct": 92.0, "ambient_humidity": 70.0},
    {"temp_c": 55.0, "vibration_mm_s": 1.2, "pressure_kpa": 210.0,
     "hours_since_service": 800.0, "load_pct": 30.0, "ambient_humidity": 40.0},
]


def get_fqdn(endpoint: str) -> str:
    """Look up the Container App's public FQDN."""
    result = subprocess.run(
        ["az", "containerapp", "show",
         "--name", endpoint,
         "--resource-group", AZURE_RESOURCE_GROUP,
         "--query", "properties.configuration.ingress.fqdn",
         "-o", "tsv"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def run_smoke(adapter, fqdn: str) -> int:
    print(f"\nSmoke testing {len(SMOKE_PAYLOADS)} payloads against https://{fqdn}/predict")
    for i, payload in enumerate(SMOKE_PAYLOADS, 1):
        try:
            result = adapter.invoke(fqdn, payload)
            prob = result.get("probability", 0.0)
            ver = result.get("model_version", "?")
            print(f"  [{i}] probability={prob:.4f}  model_version={ver}")
        except Exception as e:
            print(f"  [{i}] FAILED: {e}")
            return 1
    print("\nSmoke test PASSED")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="name:version, e.g. itcs355-6688063:2")
    ap.add_argument("--endpoint", required=True, help="Container App name")
    ap.add_argument("--instance", default="B1s", help="unused on Container Apps")
    ap.add_argument("--smoke-only", action="store_true",
                    help="Skip deployment, only run smoke tests on an existing app")
    args = ap.parse_args()

    cfg = config.load(strict=False)
    adapter = get_adapter(cfg)

    if args.smoke_only:
        fqdn = get_fqdn(args.endpoint)
        return run_smoke(adapter, fqdn)

    if not args.model:
        ap.error("--model is required unless --smoke-only is set")

    print(f"deploying {args.model} to endpoint '{args.endpoint}'...")
    fqdn = adapter.deploy(args.model, args.endpoint, args.instance)
    print(f"endpoint live at https://{fqdn}")

    return run_smoke(adapter, fqdn)


if __name__ == "__main__":
    raise SystemExit(main())
