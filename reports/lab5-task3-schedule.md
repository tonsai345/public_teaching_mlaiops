
# Lab 5 Task 3 — Scheduled retraining and the trigger question

`pipeline.yaml` schedules the pipeline with cron `0 2 * * 0` — every Sunday at
02:00. The question this task asks is not "does the schedule run?", it is
"**what should actually trigger a retrain?**"

## The three strategies, for this system

| Strategy | When it is right | How it fails |
|---|---|---|
| **Fixed schedule** (Sunday 02:00) | The input distribution is stable across days; the failure process changes slowly relative to model age. A weekly retrain keeps the model within a bounded staleness of the current sensor fleet. | The model ships every Sunday whether or not it needs to. If the fleet is static and the sensor data is stable, 51 of 52 retrains per year are wasted compute. Worse: if the failure process *shifts mid-week* (a manufacturing process change, a batch of defective bearings), the model is up to 7 days stale at the moment it matters most. |
| **Data-volume threshold** (retrain when N new labelled readings accumulate) | Labels arrive late but reliably; the model needs enough new examples to learn something new. | Training on a threshold means you can train too early (the threshold fires on 50 new rows from one machine — sample noise) or too late (the threshold doesn't fire because the *rate* of labels drops even though the *distribution* shifted). It measures the wrong quantity: how much data, not whether the data is different. |
| **Drift-triggered** (retrain when a monitor detects distribution shift) | The input distribution moves and you want to react within hours, not days. Aligns retraining cost with actual need: no drift, no retrain. | If the upstream sensor data is corrupted — a calibration bug, a stuck sensor emitting the same value, a units change — the drift detector fires, the pipeline retrains on the corrupted data, and the gate (if it's comparing against the previous model on the *same* corrupted test split) may pass. The model deployed Monday is worse than the one retired Sunday. Drift-triggered retraining on corrupted upstream data can destroy a working model faster than any schedule would, because a schedule retrains on *fresh* data — the drift detector retrains on whatever arrived, fresh or not. |

## Which strategy I chose, and why

**Fixed schedule (weekly)** with the **gate as the second line of defence**.

Justification: the underlying failure process is a wear-and-tear phenomenon
(`temp_c` and `hours_since_service` carry the strongest signal), so the decision
boundary moves slowly. A weekly retrain is enough to keep up. The gate ensures
that a retrain that produces a worse model — whether because of data drift,
corruption, or just noise — does **not** replace the production model. That
combination (schedule + gate) means:

- the model is refreshed on a known cadence
- a bad retrain is rejected by the gate rather than silently deployed
- the staleness bound is 7 days, acceptable for slow wear failure

## Worst case

The worst case of the chosen strategy is a **mid-week process change** — an
upstream production line changes its operating envelope on Tuesday, the model
was trained on Sunday, and predictions are wrong for up to 5 days before the
next retrain fires. That window is acceptable for this system because the
operator triages predictions before action; it is not acceptable for an
autonomous shutdown controller. If this system drove automatic maintenance
scheduling without human review, I would move to drift-triggered + gate, and
accept the corrupted-upstream risk because the alternative (up to 5 days of
stale predictions) is worse for the operator.

## If I moved to drift-triggered

The pipeline would gain a `monitor` step ahead of `ingest`:

The gate becomes more important, not less: drift-triggered retraining on
corrupted data can pass a naive gate if the "test set" is also corrupted. The
fix is a **frozen golden test set** — a held-out set from a known-good period
that every retrain is evaluated against. Without that, drift-triggered retraining
is a way to launder corrupted data into a production model.
EOF

cat reports/lab5-task3-schedule.md
