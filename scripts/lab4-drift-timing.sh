#!/bin/bash
set -e
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] START"

python scripts/make_dataset.py > /dev/null
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] reference ready"

python scripts/inject_drift.py --feature temp_c --mode shift --magnitude 6 > /dev/null
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] INJECTED"

python -m monitoring.drift --current data/current.csv --emit 2>&1 | grep -E "ALERT|temp_c" || true
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ALERT FIRED"
