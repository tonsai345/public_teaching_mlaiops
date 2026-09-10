Task 2: 
I would drop the hash-pinned first, becuase it's the least critical under time pressure, as the requirement.txt library can work
even with minor version change, they would be lower risk using different version

Task 6:
## Problem

Predict machine failures from industrial sensor readings (temperature, pressure, vibration, etc.). The goal is a training pipeline that any stranger can reproduce with one command.

## Data

Synthetic sensor data generated deterministically by `scripts/make_dataset.py` — 6,000 rows, 240 machines, 9 features, 11.7% positive rate. Versioned with DVC, stored in Azure Blob.

## One Command

make reproduce

## Expected metric tolerance and duration

Metric and Tolerance: test_roc_auc: 0.8482 ± 0.0100
Duration: 5–8 minutes Docker build: 2–3 min, training: 2–4 min 
