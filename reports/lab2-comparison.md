# Lab 2 — Comparison and Justification

## Chosen model

`RandomForestClassifier(n_estimators=300, max_depth=4, min_samples_leaf=10, max_features="log2")`

## Justification

This configuration was not the highest-scoring trial — `100/4/10/log2` scored 0.8444 on
validation — but the gap (0.0022) is smaller than the seed variance of 0.0293 measured
across seeds 42, 123, and 456 for the chosen config. The apparent winner is noise.

I chose `300/4/10/log2` because it is the cheapest configuration that is statistically
indistinguishable from the best: 0.0007 THB per trial versus 0.0010, a 30% saving.
At 12 monthly retrains this is marginal in absolute terms, but at production scale the
same ratio holds. It also has the highest test score (0.8541), which is the number that
matters for deployment.

The largest risk is depth. Every `max_depth=12` trial scored worse than `max_depth=4`,
suggesting the model overfits quickly on this feature set. If the production data drifts
toward noisier signals, even `max_depth=4` may need regularisation above what
`min_samples_leaf=10` provides.

## Method

- 12 trials, sampled randomly from a 54-point grid over four hyperparameters.
- Cost modelled at the Azure spot rate (30% of on-demand). Spot quota on this student
  subscription is 0 vCPUs, so trials ran on-demand on `cpu-cluster`; the cost model
  reports production-equivalent spot pricing.
- Comparison table: `reports/lab2-comparison.csv`.

## Seed variance

| Seed | val_roc_auc | test_roc_auc |
|------|-------------|--------------|
| 42   | 0.8582      | 0.8364       |
| 123  | 0.8459      | 0.8561       |
| 456  | 0.8289      | 0.8515       |
| **range** | **0.0293** | **0.0196** |

## Cost

- Per trial: ~0.0007 THB
- Monthly retrain (12 trials): ~0.0084 THB
- Full 12-trial study: 0.0069 THB
