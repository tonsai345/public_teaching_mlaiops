"""Local sequential runner for pipeline/pipeline.yaml."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "pipeline" / "pipeline.yaml"


def main() -> int:
    raw = SPEC.read_text()
    for key, value in os.environ.items():
        raw = raw.replace(f"${{{key}}}", value)
    spec = yaml.safe_load(raw)

    steps = spec["steps"]
    outputs: dict[str, dict[str, Path]] = {}
    tmp = Path(tempfile.mkdtemp(prefix="itcs355-pipeline-"))
    print(f"work dir: {tmp}")

    for step in steps:
        name = step["name"]
        print(f"\n=== {name} ===")

        cmd_str = " ".join(step["command"])

        outs = {}
        for out_name in step.get("outputs", []):
            d = tmp / name / out_name
            d.mkdir(parents=True, exist_ok=True)
            outs[out_name] = d
            cmd_str = cmd_str.replace(f"${{{{outputs.{out_name}}}}}", str(d))

        for inp in step.get("inputs", []):
            found = False
            for prev_name, prev_outs in outputs.items():
                if inp in prev_outs:
                    cmd_str = cmd_str.replace(
                        f"${{{{inputs.{inp}}}}}", str(prev_outs[inp])
                    )
                    found = True
                    break
            if not found:
                print(f"ERROR: no producer for input {inp!r}")
                return 1

        env = os.environ.copy()
        if name == "validate":
            env["DATA_PATH"] = str(outputs["ingest"]["raw_data"] / "sensors.csv")

        print(f"running: {cmd_str}")
        result = subprocess.run(cmd_str, shell=True, cwd=REPO, env=env)
        if result.returncode != 0:
            print(f"\nSTEP {name} FAILED (exit {result.returncode})")
            print("Pipeline aborted — register/deploy will NOT run.")
            return result.returncode

        outputs[name] = outs
        print(f"step {name} ok")

    print(f"\nPipeline completed. Artifacts under {tmp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
