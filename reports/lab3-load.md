# Lab 3 — Load Test Results

## Stated target (chosen before measuring)

**p95 < 500ms** at **10 VUs**, with **error rate < 1%**.

Rationale: the container is 0.5 vCPU / 1 GB RAM serving a 300-tree RandomForest.
Warm inference is sub-100ms server-side; 500ms gives headroom for network,
scale-from-zero transients, and the occasional slow request without masking
real saturation. A target chosen after seeing the numbers is not a target.

## Endpoint

`https://itcs355-serve.lemonriver-4fb1eda0.koreacentral.azurecontainerapps.io/predict`

- Container image: `itcs3556688063acr.azurecr.io/itcs355-serve:v1789976473`
- Min replicas: 0, Max replicas: 3
- Model: `itcs355-6688063` version 2, loaded from Blob at cold start
- Instance size (unless noted): **0.5 vCPU / 1 GB**

## Results at three concurrency levels (0.5 vCPU / 1 GB)

| VUs | Throughput (req/s) | p50 | p95 | Errors | p95 target met? |
|-----|-------------------|-----|-----|--------|-----------------|
| 1   | 9.03              | 108.7 ms | **120.0 ms** | 0.00% | ✅ |
| 10  | 56.81             | 136.7 ms | **331.6 ms** | 0.00% | ✅ |
| 50  | 161.8             | 198.1 ms | **799.4 ms** | 0.01% | ❌ |

**Breaking concurrency: ~30 VUs.** At 50 VUs, p95 = 799ms — 60% above the
500ms target. Throughput scales sublinearly past 10 VUs (2.9× for 5× load),
indicating CPU saturation at 0.5 vCPU.

## Cold start

The 1 VU run included a cold start (min replicas = 0). The 10 VU run's
`max=9.21s` captured a second cold start. Cold-start latency is ~3–10s and
is **excluded** from steady-state p95 figures.

## Batch size — `/predict/batch` vs 100 × `/predict`

| Metric | Single `/predict` | Batch of 100 | Ratio |
|--------|-------------------|--------------|-------|
| p50    | 145.0 ms          | 116.7 ms     | 0.80× |
| p95    | 169.7 ms          | **148.0 ms** | 0.87× |
| max    | 9.89 s (cold)     | 334.8 ms     | —     |

**Batch wins by ~115×** per prediction. One batch call for 100 predictions
costs 0.87× the latency of a single call — 1.48 ms/prediction vs 170 ms.
This is the strongest result from Task 3.

## Payload size — small vs inflated JSON

| Metric | Small payload | Large payload | Delta |
|--------|--------------|---------------|-------|
| p50    | 112.3 ms     | 111.6 ms      | −0.7 ms |
| p95    | 157.2 ms     | **158.1 ms**  | +0.9 ms (**+0.6%**) |

**Payload size is irrelevant.** The extra bytes (6 floats with 15 decimal
places) add 0.6% to p95 — within noise. Serialization is not the bottleneck;
inference time dominates.

## Instance size — 0.5 vCPU vs 1.0 vCPU at 10 VUs

| Config | Throughput | p50 | p95 | Errors |
|--------|-----------|-----|-----|--------|
| 0.5 vCPU / 1 GB | 56.8 req/s | 136.7 ms | **331.6 ms** | 0.00% |
| **1.0 vCPU / 2 GB** | **76.0 req/s** | **116.6 ms** | **164.0 ms** | 0.00% |
| Change | **+34%** | −15% | **−50%** | — |

**Doubling the CPU cut p95 in half and lifted throughput by a third.**
The 0.5 vCPU container is CPU-bound at 10 VUs.

**Cost delta:** ~2× (0.5 vCPU / 1 GB ≈ $0.000012/s/replica; 1.0 vCPU / 2 GB
≈ $0.000024/s/replica).

**Verdict:** if the p95 target is tight (< 200ms), the larger instance is
worth it. If the target is loose (< 500ms), 0.5 vCPU meets it and is 2× cheaper.

## Cost per 1,000 predictions (see Task 5)

## Raw output

Full k6 output for all runs is in the git history of this commit. Key lines:
