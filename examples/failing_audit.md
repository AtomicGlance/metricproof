# Broken SaaS retention metric audit

**Audit result: FAIL** — 0 passed, 4 failed, 0 errors.

## Dataset inventory

| Dataset | Rows |
|---|---:|
| headline | 1 |
| segments | 2 |
| cohorts | 3 |
| baseline | 7 |
| evaluated | 6 |

## Checks

| Status | Check | Type | Finding |
|---|---|---|---|
| FAIL | activation-rate-recomputes | ratio_consistency | 1 reported rate(s) do not match their components. |
| FAIL | segment-mrr-ties-to-headline | reconciliation | The two sum aggregates differ by 3.53%. |
| FAIL | eligible-population-survives | population_preserved | Evaluated population preserves 85.7%; 1 missing and 0 unexpected. |
| FAIL | retention-cohorts-are-valid | cohort_integrity | 2 cohort integrity issue(s) found. |

## Actionable failures

### activation-rate-recomputes

- **Why it matters:** A plausible percentage can still be wrong when its denominator changed.
- **Suggested fix:** Recompute the rate from the audited numerator and denominator at the same grain.
- **Observed:** `{"violations": 1}`
- **Expected:** `{"formula": "activated_accounts / eligible_accounts", "tolerance": 0.0001}`
- **Evidence sample:** `[{"row": 2, "numerator": 52.0, "denominator": 80.0, "reported_rate": 0.72, "computed_rate": 0.65, "difference": 0.07}]`

### segment-mrr-ties-to-headline

- **Why it matters:** Dashboard totals should tie back to their source or segment breakdown.
- **Suggested fix:** Compare filters, date cutoffs, join cardinality, and metric definitions.
- **Observed:** `{"left": 41000.0, "right": 42500.0, "relative_difference": 0.03529411764705882}`
- **Expected:** `{"maximum_relative_difference": 0.0}`
- **Evidence sample:** `[{"left": 41000.0, "right": 42500.0, "absolute_difference": 1500.0, "relative_difference": 0.03529412}]`

### eligible-population-survives

- **Why it matters:** Dropped inactive or unmatched entities create survivorship bias and inflate KPIs.
- **Suggested fix:** Start from the eligible baseline population and left join activity onto it.
- **Observed:** `{"coverage": 0.8571428571428571, "missing": 1, "unexpected": 0}`
- **Expected:** `{"minimum_coverage": 1.0, "unexpected_entities_allowed": false}`
- **Evidence sample:** `[{"key": "A07", "issue": "missing from evaluated population"}]`

### retention-cohorts-are-valid

- **Why it matters:** Changing denominators or malformed cohort shapes can turn retention into a misleading KPI.
- **Suggested fix:** Freeze cohort membership at entry, retain zero-activity rows, and recompute each rate.
- **Observed:** `{"cohorts": 1, "violations": 2}`
- **Expected:** `{"stable_denominator": true, "period_zero_rate": 1.0, "retained_not_above_size": true, "monotonic": true, "tolerance": 0.0001}`
- **Evidence sample:** `[{"cohort": "2025-01", "period": 0, "issue": "period-zero retention is not 100%", "reported": 0.75}, {"cohort": "2025-01", "period": 2.0, "issue": "retained count increases in a strict retention cohort", "previous": 2.0, "current": 3.0}]`
