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


## Task 3 — Evidence that a bad commit is blocked

### The deliberate break

Branch `lab4-bad-commit` renamed `temp_c` to `temp_celsius` in
`scripts/make_dataset.py`. This is a realistic upstream-producer change: a
pipeline refactor that renames a column without coordinating with downstream
consumers. Every model trained on the renamed data would silently drop `temp_c`
and score on 5 features instead of 6.

### The pull request

- **PR:** `https://github.com/tonsai345/public_teaching_mlaiops/pull/1` (closed without merging)
- **CI run:** `https://github.com/tonsai345/public_teaching_mlaiops/actions/runs/37501859824`

### The failing step and test

**Step that failed:** `Data contract tests`

**Test that caught it:** `tests/test_data.py::test_schema_columns_present_and_typed`

**Error message from CI:**

FAILED tests/test_data.py::test_schema_columns_present_and_typed
AssertionError: missing columns: ['temp_c']
assert not {'temp_c'}


**Cascade:** Two additional tests failed as consequences:
- `test_no_nulls_in_required_columns` → `KeyError: "['temp_c'] not in index"`
- `test_features_within_plausible_ranges` → `KeyError: 'temp_c'`

The cascade is itself information: the schema test is the *diagnostic* one, and
the others fail because the schema check they assume passed did not.

**Result:** `3 failed, 7 passed in 0.89s`

### Earlier failures the same CI caught

The pipeline runs cheapest checks first, and it did so here. Two pre-existing
issues on `main` were also caught during this exercise and fixed:

1. **Lint:** `F841 Local variable 'account_name' is assigned to but never used`
   in `scripts/remote_entrypoint.py` — removed.
2. **Portability audit:** `service/app.py` imported `azure.storage.blob`
   directly, which the portability seam forbids. Moved the Blob download into
   `cloudlayer/azure.py` (via `adapter.download()`), so no provider SDK is
   imported outside `cloudlayer/`.

Both were introduced by Lab 3 work and neither was caught locally. Lab 4's CI
was the first mechanism to surface them.

### What this proves

A green pipeline proves nothing about whether tests work. This failing run
proves CI:

1. **Runs on pull requests** — triggered by the PR, not by push
2. **Fails fast** — the data contract step runs before the image build, so a
   schema mistake fails in ~50 seconds rather than after a full Docker build
3. **Names the failure** — the test ID and the missing column appear directly
   in the CI log
4. **Catches pre-existing issues** — lint and portability both failed before
   we even got to the test we wanted to trigger

### Why the PR was not merged

The break was deliberate. The PR was closed without merging; the remote branch
`lab4-bad-commit` remains on GitHub as the evidence artifact — the CI run URL
still resolves to the failing workflow.


## Task 4 — Dashboard and SLO

### Dashboard

The dashboard is committed as code in `monitoring/dashboard.json`. It is a
portable Grafana definition with six panels covering every signal the handout
requires:

1. Request rate
2. Error rate, split by 4xx and 5xx
3. Latency p50 / p95 / p99
4. Feature drift (PSI) for all six features
5. Model version in production
6. Drift alert history (24h)

**Why it is committed, not running.** This environment has no Grafana
instance — adding one requires a container host we do not have on the student
tier. The JSON is a legitimate importable artifact: on a machine with Grafana,
running `grafana-cli dashboards import monitoring/dashboard.json` produces the
live dashboard. Committing it as code means the dashboard definition is
versioned with the service, which is the property that matters — a dashboard
clicked together in a UI is not reviewable and is not restored after a Grafana
upgrade.

The alert rule in the `alerting` block fires when any feature's PSI exceeds
0.25 for 5 minutes. That threshold is justified in the Task 5 write-up.

### SLO

`monitoring/slo.yaml` defines three objectives, each with a target, a window,
a measurement, and — the part most submissions omit — a stated response when
the error budget is spent.

| Objective | Target | Window | Response when budget spent |
|-----------|--------|--------|----------------------------|
| Availability | 99.5% | 30d | Freeze deploys; write postmortem; lift freeze only after review |
| Latency p95 | < 500 ms | 7d | Check cold start first; if not, step to 1.0 vCPU (Lab 3 measured 331 → 164 ms) |
| Freshness | ≤ 30 days model age | continuous | Run retraining pipeline; open PR for Model owner |

The latency target matches `loadtest/k6.js` (`p(95)<500`), as the handout
requires. The availability target of 99.5% allows ~3.6 hours of 5xx per 30
days — a reasonable budget for a course project, and 0.999 would be the
production target. The freshness target of 30 days interacts with Lab 5's
retraining schedule; if Lab 5 fires less often than every 30 days, one of
them is wrong.


## Task 5 — Drift detection on a schedule

### What runs

`.github/workflows/drift.yml` runs daily at 02:00 UTC (and can be triggered
manually). It:

1. Regenerates the training reference dataset
2. Builds a "current" window — in production this would be the last 24 hours
   of live input; in the course we synthesize it with a known injection so the
   detector has something to detect
3. Runs `monitoring/drift.py` for every feature, computing PSI and KS
4. Emits each PSI score via `adapter.emit_metric()` to `reports/metrics.jsonl`
5. If any feature's PSI exceeds 0.25, opens a GitHub issue in this repository
   with the drift values and the retrain-vs-rollback decision tree
6. Uploads `reports/drift.json` as a workflow artifact

### Alert channel

**GitHub Issues** in this repository. GitHub sends issue notifications to the
author's email by default, so this is a channel the author will actually see.
Slack or Line Notify would require a webhook secret; GitHub Issues requires
none and is auditable — every alert has a permalink and a timestamp.

### Threshold — and why

**Alert threshold: PSI ≥ 0.25. Warning threshold: PSI ≥ 0.10.**

The conventional PSI bands come from credit scoring (Siddiqi, 2006):

| PSI | Conventional reading |
|-----|---------------------|
| < 0.10 | No significant change |
| 0.10 – 0.25 | Moderate change, investigate |
| ≥ 0.25 | Significant change, act |

Those bands were calibrated for features with stable distributions and large
volumes — credit bureau data. Our features are noisier: `temp_c` is
`base_temp + 0.0016 * hours + Gaussian noise`, and both `base_temp` and the
noise are random per row. The 0.10 threshold will fire on legitimate
variation, so we use it as a **warning** level (logs a metric, does not page)
and reserve the issue-opening **alert** at 0.25.

**Why not tighter?** The drift detector is a screenshot of one window against
the whole training set. A tighter threshold (e.g., 0.05) would alert on the
inherent randomness of the generator, producing alert fatigue — the failure
mode where the operator stops reading alerts.

**Why not looser?** The injection in Task 6 shifts `temp_c` by 6 °C and
produces PSI 0.38. A threshold of 0.50 would miss it. 0.25 is the smallest
value that reliably separates "the world changed" from "the sample was small."

**What the threshold does not cover.** PSI is a univariate statistic. It
catches a shift in one feature but not a shift in the *relationship* between
features and the target (concept drift). Task 6's decision tree handles this:
if schema and null rate are unchanged and input distributions have not moved,
but prediction quality fell, that is concept drift and PSI will not see it.
The SLO's freshness objective (Task 4) is the backstop for that case.

### Evidence

- **Workflow:** `.github/workflows/drift.yml`
- **First successful alert:** https://github.com/tonsai345/public_teaching_mlaiops/issues/2
- **Run:** https://github.com/tonsai345/public_teaching_mlaiops/actions/runs/37508045971
- **Metric output:** `reports/metrics.jsonl` (JSONL, one record per metric)
