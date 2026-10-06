# Lab 4 Task 6 — Injected Drift Post-Mortem

## Setup

- **Injection:** `python scripts/inject_drift.py --feature temp_c --mode shift --magnitude 6`
  shifts the `temp_c` distribution by +6 °C, from mean 79.58 to mean 85.58.
- **Detection:** `python -m monitoring.drift --current data/current.csv --emit`
  compares the shifted window to `data/raw/sensors.csv` (the training reference).
- **Alerting:** the GitHub Actions drift workflow opens an issue when any
  feature's PSI exceeds 0.25.

## Timeline (UTC)

| Time | Event |
|------|-------|
| 18:05:51 | START — timing script begins |
| 18:05:58 | Reference dataset generated |
| **18:06:04** | **INJECTED — temp_c shifted by +6 °C** |
| **18:06:11** | **ALERT FIRED — PSI 0.383, threshold 0.25 crossed** |

**Detection latency: 7 seconds** from injection to detector output.

The GitHub Actions workflow adds ~30–60 seconds of step overhead (checkout,
Python install, dependency install), so end-to-end injection-to-issue is
under 2 minutes when the workflow is triggered. In production, the schedule
interval dominates: a daily cron means up to 24 hours between the real-world
event and the alert, which is why the recommendation below shortens it.

## Evidence

- **Alert:** https://github.com/tonsai345/public_teaching_mlaiops/issues/2
- **Workflow run:** https://github.com/tonsai345/public_teaching_mlaiops/actions/runs/37508045971
- **Metric output:** `reports/metrics.jsonl`
- **Timing script:** `scripts/lab4-drift-timing.sh`

**Detector output:**
feature psi ks verdict
temp_c 0.38333 0.24567 significant
vibration_mm_s 0.00000 0.00000 stable
pressure_kpa 0.00000 0.00000 stable
hours_since_service 0.00000 0.00000 stable
load_pct 0.00000 0.00000 stable
ambient_humidity 0.00000 0.00000 stable

## Five-line post-mortem

**What fired:**
Drift alert on `temp_c` (PSI 0.383, KS 0.246). Reference mean 79.58, current
mean 85.58 — a +6 °C shift. Other features unchanged (PSI 0.000).

**True cause:**
The injected shift simulates a producer-side change — a calibration offset, a
sensor firmware update, or an upstream transform that added 6 to every
reading. It is **not** a change in the real-world machine behaviour; the
machines are the same, the readings are biased.

**Retrain, roll back, or no action — and why:**
**No action.** The schema is unchanged (all columns present, types correct),
the null rate is unchanged, and the shifted distribution is an artefact of
the injection — not a persistent change to the world. Retraining on this data
would bake a 6 °C bias into the model, corrupting it against the true sensor
distribution. The correct response is to **investigate the producer**,
confirm it is the injection and not a real calibration event, and do nothing
until the producer is fixed. If the shift were confirmed as a legitimate,
persistent change (e.g., the sensors were genuinely recalibrated), then
retraining would be correct — but only after the reference dataset is updated
to reflect the new baseline.

**What this would have cost if unnoticed for a week:**
Every `/predict` call for a week would score against a model trained on
`temp_c ≈ 79.6`, receiving `temp_c ≈ 85.6`. The model's `temp_c` coefficient
is positive, so predicted failure probabilities would be systematically
inflated. At ~10,000 predictions/day, a 10% increase in false positives is
**~7,000 unnecessary maintenance tickets** in a week. The larger cost is the
model's credibility: a model that is wrong for a week is harder to trust
after the fix than before the drift.

**How to prevent or detect it faster:**
Two changes:

1. **Shorter detection window.** The scheduled run is daily. A 1-hour cron
   would cut detection latency from up to 24 hours to at most 1 hour, at the
   cost of 24× the workflow runs. For this feature — where a silent producer
   bug is the realistic risk — 1 hour is the right trade.
2. **Emit schema and null-rate checks before the PSI check.** The decision
   tree asks "did the schema or null rate change?" first for a reason: a
   producer bug is caught by a schema check in milliseconds. Adding those
   checks to the workflow would let the alert say "producer broke" instead of
   "PSI moved" for the most common cause.
