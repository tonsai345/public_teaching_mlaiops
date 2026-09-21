# Lab 3 Task 5 — Cost per 1,000 Predictions

## Method
cost_per_1000 = (hourly_rate_THB / 3600) * (1000 / throughput_rps)
/ utilisation

Where:
- `hourly_rate_THB` is the Container Apps consumption rate for the instance
- `throughput_rps` is the measured steady-state throughput at 10 VUs
- `utilisation` is the fraction of wall-clock time the container is actually
  serving traffic (the most fragile number in this calculation)

## Inputs (measured)

| Instance | Hourly rate (THB) | Throughput at 10 VUs | Source |
|----------|-------------------|---------------------|--------|
| 0.5 vCPU / 1 GB | ~1.55 | 56.8 req/s | Task 3 load test |
| 1.0 vCPU / 2 GB | ~3.11 | 76.0 req/s | Task 3 load test |

Container Apps consumption pricing as of the last rate check:
- 0.5 vCPU / 1 GB: $0.000012/s per active replica → $0.0432/hr → 1.55 THB/hr
- 1.0 vCPU / 2 GB: $0.000024/s per active replica → $0.0864/hr → 3.11 THB/hr

USD/THB = 36 (same rate used in Lab 2 cost model).

## Cost per 1,000 predictions at different utilisation assumptions

| Utilisation | 0.5 vCPU / 1 GB | 1.0 vCPU / 2 GB |
|-------------|-----------------|-----------------|
| 100% (saturated) | **0.0076 THB** | **0.0114 THB** |
| 50% | 0.0152 THB | 0.0228 THB |
| 10% | 0.0758 THB | 0.1138 THB |
| 1% | 0.758 THB | 1.138 THB |

## The utilisation assumption

**Stated explicitly: 10% utilisation.** This is where the number is most
fragile. At 10% utilisation, the container serves traffic for 6 minutes out
of every hour and idles for 54. The 1.0 vCPU config costs **1.14 THB per
1,000 predictions**; the 0.5 vCPU config costs **0.76 THB**.

If real utilisation is closer to 1% (a realistic level for a lab-scale
service), costs rise 10×. If it's 100% (a saturated production service),
costs fall 10×.

## Batch vs online — when is batch cheaper?

At 100% utilisation, the online endpoint costs **0.0114 THB per 1,000
predictions**. A batch job on a `Standard_DS2_v2` training node (2 vCPU,
~7.30 THB/hr from `src/costs.py`) processing at the same throughput as the
online endpoint would cost:


cost_per_1000_batch = (7.30 / 3600) * (1000 / 76.0) = 0.0267 THB


**The online endpoint is cheaper than batch** at this throughput, because
the batch node is oversized for inference. Batch inference becomes cheaper
only when:
1. **Volume is high enough** to amortise node startup (batch jobs have
   provisioning overhead the online endpoint doesn't pay)
2. **Latency requirements are loose** — batch doesn't need sub-second response
3. **Utilisation is low** — if you only serve 1,000 predictions per hour, an
   always-on endpoint wastes 99% of its billed time; batch runs for seconds.

**Crossover rule:** batch wins when `predictions_per_hour < throughput_rps * 3600 * utilisation`,
i.e., when the online endpoint is idle more than ~90% of the time.
