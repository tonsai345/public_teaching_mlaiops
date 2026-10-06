# ITCS355 Lab 4 — CI/CD, Observability, and Drift

## Task 1 — What each data contract test would have caught

Data contract tests fail when an **upstream producer** changes something, even though
your code is untouched. Each one below maps to a real production incident.

| Test | Incident it would have caught |
|------|-------------------------------|
| `test_schema_columns_present_and_typed` | An upstream ETL renames `vibration_mm_s` to `vibration_mm_s_v2`. Without this test, the pipeline silently drops the column, trains on the remaining 5 features, and reports a slightly-lower metric. In production, the model scores with the missing feature defaulted to NaN, producing confidently wrong predictions. |
| `test_no_nulls_in_required_columns` | A sensor goes offline and the upstream producer writes `null` instead of dropping the row. Training tolerates nulls (pandas drops them), so the model trains on fewer rows. In production, `/predict` receives `{"vibration_mm_s": null}`, pandas raises inside `_score`, and every request 500s. |
| `test_features_within_plausible_ranges` | A unit change in the upstream producer — Celsius to Fahrenheit for `temp_c`, or kPa to PSI for `pressure_kpa`. The values still look numeric, the schema is unchanged, but the model is now scoring on a 3× shifted distribution. No metric would catch this until accuracy visibly dropped. |
| `test_target_is_binary_and_not_degenerate` | A label pipeline bug writes `2` for "unknown failure type" instead of `1`. Training fails silently — the model is now a 3-class classifier with a 2-class interface. In production, `predict_proba()[:, 1]` reads the wrong column. |
| `test_identifier_is_unique` | A retry in the ingestion pipeline double-writes rows. The dataset grows by 2×, the split is no longer by machine, and the validation score inflates because duplicate rows leak between train and val. |
| `test_no_machine_leaks_across_splits` | The exact silent error the lab calls out — readings from one machine appearing in both train and validation. The model reports val ROC 0.85, then scores 0.60 in production because it memorised the machine, not the failure pattern. |

## Task 1 — Model behaviour tests

Behaviour tests fail when the **model** changes, not the data. Two incidents they catch:

- `test_known_healthy_machine_scores_low` — a retrain on corrupted labels flips the model's
  sign. Accuracy is still 0.80, but every healthy machine is now flagged as at-risk.
- `test_risk_increases_with_wear` — a feature-engineering change drops `hours_since_service`
  from the model. Random Forest stops being monotonic in wear, and the model becomes
  physically implausible even though no metric moves much.

## Task 1 — Integration test

The integration test builds the serving image, starts the container, and hits `/predict`
with a known payload. It catches what unit tests cannot: the `Dockerfile.serve` missing a
COPY line, a base image change breaking the CMD, or the model artifact not making it into
the layer.


## Task 2 — CI/CD pipeline

### What works

- **CI** (`.github/workflows/ci.yml`) runs on every PR and push to `main`:
  lint → portability audit → data generation → data contract tests →
  model behaviour tests → service tests → build both images → integration test.
- **CD** (`.github/workflows/cd.yml`) runs on green CI on `main`:
  authenticates to ACR, builds the serving image tagged by commit SHA, pushes it.

### What is a documented gap

The **deploy leg** of CD is a documented gap, not a bug. Deploying to Azure
Container Apps from GitHub Actions requires either:

1. **OIDC federation** — requires `az ad app federated-credential create`,
   which needs Entra ID app-creation permission. Azure for Students on a
   university tenant blocks this: `az ad sp create-for-rbac` fails with
   `Insufficient privileges to complete the operation`.
2. **A service principal stored as a secret** — requires the same permission
   to create the service principal in the first place.

Neither is available on this subscription. The push leg works because ACR
admin credentials are available; the deploy leg is performed locally by the
developer after CI passes.

### Secrets

- `ACR_USERNAME` / `ACR_PASSWORD` — ACR admin credentials, stored as GitHub
  repository secrets (not committed).
- The `AZURE_CREDENTIALS` secret is **not set**, and its absence is what
  causes the deploy step to log the gap and skip.

A long-lived credential is worse than OIDC, but a repository secret satisfies
the handout's wording ("repository secret store") — the constraint is real,
not a shortcut.
