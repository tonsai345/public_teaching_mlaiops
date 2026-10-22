"""Lab 5 — the registration gate.

Compares a candidate against the currently registered production model. Exits non-zero
when the candidate should NOT be registered, which is what makes the pipeline condition
real rather than decorative.

    python scripts/evaluation_gate.py --metrics reports/metrics.json

Outputs a `gate_decision.json` next to the metrics when `--decision-out` is given, which
is what the pipeline's `condition: gate_decision == 'pass'` reads.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MIN_ABSOLUTE = 0.75
MIN_IMPROVEMENT = 0.002


def _read_incumbent_from_registry(metric: str) -> float | None:
    model_name = os.environ.get("MODEL_REGISTRY_NAME")
    if not model_name:
        print("MODEL_REGISTRY_NAME not set — cannot read incumbent, treating as first run")
        return None
    try:
        from azure.ai.ml import MLClient
        from azure.identity import AzureCliCredential
        from src import config as _cfg
        _cfg.load(strict=False)
        import os as _os
        ml_client = MLClient(
            AzureCliCredential(),
            _os.environ["AZURE_SUBSCRIPTION_ID"],
            _os.environ.get("AZURE_RESOURCE_GROUP", "itcs355-6688063-rg"),
            _os.environ.get("AZURE_WORKSPACE", "itcs355-workspace"),
        )
        versions = sorted(
            (m.version for m in ml_client.models.list(name=model_name)),
            key=lambda v: int(v) if v.isdigit() else 0,
        )
        if not versions:
            print(f"no versions of {model_name} — first run")
            return None
        model = ml_client.models.get(model_name, version=versions[-1])
        print(f"incumbent: {model_name} version {model.version}")
    except Exception as exc:
        print(f"could not read incumbent from registry ({type(exc).__name__}): {exc}")
        return None
    raw = (model.tags or {}).get("metric_test") or (model.tags or {}).get(metric)
    if raw is None:
        print(f"latest {model_name} has no metric_test tag — treating as first run")
        return None
    try:
        return float(raw)
    except ValueError:
        print(f"latest {model_name} has a non-numeric metric_test ({raw!r}) — treating as first run")
        return None


def _write_decision(path, payload):
    if path is None:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", type=Path, required=True)
    ap.add_argument("--metric", default="test_roc_auc")
    ap.add_argument("--incumbent", type=float, default=None)
    ap.add_argument("--decision-out", type=Path, default=None)
    args = ap.parse_args()

    payload = json.loads(args.metrics.read_text())
    candidate = float(payload[args.metric])
    print(f"candidate {args.metric} = {candidate:.4f}")

    def finish(decision, reason, incumbent, delta):
        print(reason)
        print(f"GATE {decision.upper()}")
        _write_decision(args.decision_out, {
            "decision": decision, "reason": reason,
            "candidate": candidate, "incumbent": incumbent, "delta": delta,
        })
        return 0 if decision == "pass" else 1

    if candidate < MIN_ABSOLUTE:
        return finish("fail", f"below absolute floor {MIN_ABSOLUTE}", None, None)

    incumbent = args.incumbent if args.incumbent is not None \
        else _read_incumbent_from_registry(args.metric)

    if incumbent is None:
        return finish("pass", "no incumbent — first registration", None, None)

    delta = candidate - incumbent
    print(f"incumbent {incumbent:.4f}  delta {delta:+.4f}  required {MIN_IMPROVEMENT:+.4f}")
    if delta < MIN_IMPROVEMENT:
        return finish("fail", f"improvement {delta:+.4f} within noise", incumbent, delta)
    return finish("pass", f"improvement {delta:+.4f}", incumbent, delta)


if __name__ == "__main__":
    raise SystemExit(main())
