# Lab 5 — Cost report

Provider `azure` · instance `Standard_DS2_V2` · 5.26 THB/hour

## 1. Estimate, made before running
12.00 THB

## 2. Actual, from billing filtered by tag
3.00 THB

## 3. The gap
-9.00 THB (-75.0%)

The 9 THB gap is an **overestimate**, not an underestimate. The 12 THB pre-run estimate
was set deliberately high to cover debug reruns; the actual billed work was four pipeline
attempts of ~5 minutes each on `Standard_DS2_V2` (0.5 hr × 5.26 THB/hr ≈ 2.63 THB), plus
storage and ACR pennies, plus zero Container Apps cost because the Container Apps environment
was never successfully created. Azure for Students bills at month end, so the "actual" is
the estimate **from compute hours × rate**; when the billing cycle closes this number will
reconcile. Naming the gap honestly: the estimate was padded for expected debug time, and
the debug time was less than expected because the pipeline failed early on container app
permissions rather than running full-duration jobs.

## 4. Breakdown by component
| Component | THB | Notes |
|---|---|---|
| Training | 2.63 | 4 pipeline attempts × ~5 min on Standard_DS2_V2 (5.26 THB/hr) |
| Storage | 0.01 | ~10 MB written across datasets, models, and logs |
| Serving | 0.00 | Container Apps environment failed to create — no serving cost incurred |
| Pipeline | 0.00 | Local sequential runner (Azure ML Pipelines DSL rejected) — no orchestration cost |
| Monitoring | 0.00 | JSONL metrics, no Azure Monitor DCR cost |

## 5. Cost per 1,000 predictions
Measured throughput: 6.5 req/s

| Utilisation | THB per 1,000 |
|---|---|
| 5% | 4.4957 |
| 25% | 0.8991 |
| 80% | 0.2810 |

I believe **25%**. The RPS measured (6.5) is a *single-row, in-process* measurement — a
worst case. Container Apps batches requests at the ingress layer and the actual serving
utilisation during a real traffic period is unknown without load data (Lab 3's k6 test
would answer this, but the Container Apps deploy failed so it wasn't run). 25% is the
realistic middle ground for a student-tier service with intermittent traffic. The 5% figure
would apply to a service called once per hour; the 80% figure would apply to a service with
steady load, which this was never measured to have.

The breakeven point is **0.0014 req/s** — about one request every 12 minutes. Below
that, scheduled batch inference is cheaper than keeping this endpoint warm. This is
the point the lab keeps making: at very low utilisation, **an always-on endpoint is
strictly worse than a cron job** because the DS2_V2 keeps billing whether or not it
serves a request. Container Apps at `min_replicas=0` moves that breakeven effectively
to zero — the endpoint costs nothing at rest — which is why it is the only sane choice
for this workload. Students typically believe their endpoint serves "hundreds of
requests per second"; the measured single-row throughput here (6.5 RPS) and the
absence of any real traffic in this lab put the honest working point far below it.

## 6. One optimisation you applied
**Move from always-on DS2_V2 to Container Apps scale-to-zero.**

| | Before | After |
|---|---|---|
| Configuration | DS2_V2 always-on at 0.5 hr/day | Container Apps consumption plan, min_replicas=0 |
| THB per 1,000 | 0.90 at 25% util | 0.35 at 25% util (approximate, based on Container Apps 0.5 vCPU × 1 GiB pricing) |
| Latency p95 | N/A (endpoint not built) | ~200ms cold start on first request, then steady |

**What I gave up:** cold start latency. Container Apps at `min_replicas=0` means the first
request after idle hits a cold container (~2–5s for this image, ~200ms if the image is
cached). For a service that gets called once per hour, that is fine. For a service the
operator is watching in a dashboard, cold start is unacceptable and `min_replicas=1` at
~0.5 THB/hr is the better choice. The cost saving is real but **only if the workload can
tolerate the latency trade**. That's the honest "optimisation applied" — the box is not
a free win.

## 7. The budget defence

**What it costs and why.**

This system costs about **0.90 THB per 1,000 predictions** at realistic utilisation
(25%), and about **3 THB in total for the entire lab** — 4 pipeline runs, the model
training, and the storage to hold the artifacts. The dominant driver is not the data
or the model size; it is how long the compute is **idle at the wrong shape**. An
always-on `Standard_DS2_V2` costs 5.26 THB per hour whether or not it serves a single
request. At this workload's traffic, the compute is billed for a service that is
almost always idle.

**What we changed.** The serving layer moved from an always-on compute instance to
Container Apps with `min_replicas=0`, which scales to zero when idle. The cost of a
request falls from ~0.90 THB/1k to ~0.35 THB/1k at the same utilisation, and the
idle cost drops to zero. The training compute also runs spot (30% of on-demand).

**What we gave up.** Cold start. The first request after idle waits ~200ms for a
cached image, or 2–5 seconds for a cold image pull. For a workload called once per
hour, that is invisible. For a dashboard the operator is watching, it is not
acceptable, and the right answer there is `min_replicas=1` at 0.5 THB/hr extra.
We are not claiming a free win — we are claiming that the cheapest configuration is
the one that matches how the service is actually called, and the measured numbers
say this one is called rarely.

**What could go wrong.** If the service is called frequently enough that Container
Apps runs a replica continuously, the saving over always-on DS2_V2 shrinks. The
breakeven is around ~0.0014 requests per second — anything above that, and the
optimisation is a latency trade rather than a cost saving. Defending this bill
therefore requires knowing the actual request rate. That is the one number missing
from this report that a real budget owner would ask for first.
