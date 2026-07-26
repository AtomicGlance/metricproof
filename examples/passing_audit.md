# SaaS retention metric audit

**Audit result: PASS** — 6 passed, 0 failed, 0 errors.

## Dataset inventory

| Dataset | Rows |
|---|---:|
| headline | 1 |
| segments | 2 |
| cohorts | 5 |
| baseline | 7 |
| evaluated | 7 |

## Checks

| Status | Check | Type | Finding |
|---|---|---|---|
| PASS | one-headline-per-month | unique_grain | 1 rows match the declared grain. |
| PASS | activation-rate-bounds | numeric_range | All 1 'activation_rate' values are within range. |
| PASS | activation-rate-recomputes | ratio_consistency | All 1 reported rates recompute correctly. |
| PASS | segment-mrr-ties-to-headline | reconciliation | The two sum aggregates reconcile. |
| PASS | eligible-population-survives | population_preserved | Evaluated population preserves 100.0% of baseline entities. |
| PASS | retention-cohorts-are-valid | cohort_integrity | All 2 cohort(s) preserve their analytical contract. |
