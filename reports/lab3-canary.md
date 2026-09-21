# Lab 3 Task 4 — Canary and Rollback

## Setup

Container Apps **express environment** does not support native traffic split
(the `ingress traffic show` command returns nothing, and `revision-suffix` is
rejected with `ExpressEnvironmentFeatureNotSupported`). Traffic split was
therefore simulated at the client level.

Two Container Apps were deployed under the same express environment:

| App | Model version | Role | FQDN |
|-----|---------------|------|------|
| `itcs355-serve` | v2 (val=0.8422, test=0.8541) | Good | `itcs355-serve.lemonriver-4fb1eda0.koreacentral.azurecontainerapps.io` |
| `itcs355-serve-canary` | v3 (val=0.8268, test=0.8415) | Canary | `itcs355-serve-canary.lemonriver-4fb1eda0.koreacentral.azurecontainerapps.io` |

The canary model is deliberately worse by a small margin — v3 is trained with
`max_depth=12, min_samples_leaf=1` (overfits), which scored val ROC 0.8268
vs v2's 0.8422. A 0.015 drop is meaningful but not obviously broken.

## Method

`scripts/canary_test.py` sends 90% of traffic to the good endpoint and 10% to
the canary, 2 requests per second for 5 minutes (600 requests total). It uses
four fixed payloads, rotates through them randomly, and tracks the mean
predicted probability from each stream.

Detection rule: after 20 samples in each stream, if `|good_mean − canary_mean| > 0.05`,
the canary is flagged as degraded.

## Results

| Stream | Mean probability | Samples |
|--------|------------------|---------|
| Good (v2) | **0.3533** | 333 |
| Canary (v3) | **0.2760** | 34 |
| **Delta** | **0.0773** | — |

**Detection at 148 seconds** from test start.

At the moment of detection (t=148s):
- Good mean: 0.3406 (n=161)
- Canary mean: 0.2100 (n=20)
- Delta: 0.1306

## Rollback

`[2026-09-21T23:21:10Z] ROLLBACK — routing 100% to good endpoint`

The rollback in this simulation is the cessation of the 10% canary traffic
split. In a native-traffic-split environment (e.g., standard Container Apps
revisions, or Azure ML managed online endpoints), the rollback would instead
be a `az containerapp ingress traffic set --revision-weight` call that shifts
100% to the good revision.

## Five-line write-up

1. **What metric revealed it:** the **mean predicted probability** across a
   fixed set of inputs. The canary shifted the mean by 0.077 (22% relative),
   well above the 0.05 detection threshold.
2. **How long detection took:** **148 seconds**, of which the first 100s were
   spent collecting 20 canary samples at the 10% split rate.
3. **What would have made it faster:** (a) a **higher canary weight**
   (e.g., 50/50 → 20 samples in ~20s instead of ~100s), or (b) **more diverse
   payloads**, since four fixed inputs may not exercise the model's full
   response surface.
4. **What would have happened at 50/50:** detection would have taken ~20s
   instead of 148s, but **half the users would have received degraded
   predictions** during that window — roughly 10× the customer impact for
   7× faster detection. 90/10 is the right trade for a small degradation;
   50/50 is only defensible if the degradation is severe enough that
   minutes of exposure are unacceptable.
5. **Was the split real evidence?** Yes — the delta between streams (0.077)
   is well above the seed variance we measured in Lab 2 (val ROC range 0.029
   across seeds 42/123/456 for the same config), so the shift is caused by
   the model version, not random variation.
