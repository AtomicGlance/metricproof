# MetricProof

**Executable checks for the assumptions behind business metrics.**

MetricProof is a small, dependency-free Python package and CLI for detecting
analytical failures that ordinary schema tests can miss: a KPI calculated from
the wrong denominator, customers silently lost before evaluation, segment
totals that do not reconcile, and malformed retention cohorts.

It was built from a practical SaaS retention problem: a dashboard value can
look plausible while still being misleading because its population or
denominator changed upstream.

## Why this project is different

Most data-quality tools are strong at generic checks such as nulls, types,
ranges, and duplicate rows. MetricProof has a narrower purpose: it turns
**metric definitions into executable evidence**.

- `ratio_consistency` recomputes a published rate from its numerator and
  denominator.
- `population_preserved` catches survivorship bias when inactive or unmatched
  entities disappear before analysis.
- `cohort_integrity` checks frozen denominators, period-zero retention, valid
  rates, and monotonic strict-retention curves.
- `reconciliation` proves that headline and segmented totals tie out.
- `unique_grain` and `numeric_range` protect the table structure and metric
  bounds supporting those business assertions.

This is a portfolio-distinctive combination, not a claim that no other
data-quality framework has related capabilities.

## Quick start

MetricProof requires Python 3.11 or newer and has no runtime dependencies.

```bash
python -m pip install metricproof
metricproof --help
```

To run the included SaaS retention audit:

```bash
git clone https://github.com/AtomicGlance/metricproof.git
cd metricproof
metricproof audit examples/retention_contract.json
```

Expected result:

```text
MetricProof: SaaS retention metric audit
Result: PASS | 6 passed, 0 failed, 0 errors

[PASS ] one-headline-per-month (unique_grain)
        1 rows match the declared grain.
[PASS ] activation-rate-bounds (numeric_range)
        All 1 'activation_rate' values are within range.
[PASS ] activation-rate-recomputes (ratio_consistency)
        All 1 reported rates recompute correctly.
[PASS ] segment-mrr-ties-to-headline (reconciliation)
        The two sum aggregates reconcile.
[PASS ] eligible-population-survives (population_preserved)
        Evaluated population preserves 100.0% of baseline entities.
[PASS ] retention-cohorts-are-valid (cohort_integrity)
        All 2 cohort(s) preserve their analytical contract.
```

Run the intentionally broken example to see the audit expose four subtle
failures:

```bash
metricproof audit examples/broken_retention_contract.json
```

The command exits with `0` when critical checks pass, `1` when a critical check
fails, and `2` when the contract or input cannot be read. That makes it useful
as a lightweight CI quality gate.

## Analytical contract

Checks live in a readable JSON contract. Dataset paths are resolved relative to
the contract file.

```json
{
  "title": "SaaS retention metric audit",
  "datasets": {
    "headline": "data/headline.csv",
    "baseline": "data/baseline_accounts.csv",
    "evaluated": "data/evaluated_accounts.csv"
  },
  "checks": [
    {
      "id": "activation-rate-recomputes",
      "type": "ratio_consistency",
      "dataset": "headline",
      "numerator": "activated_accounts",
      "denominator": "eligible_accounts",
      "rate": "activation_rate"
    },
    {
      "id": "eligible-population-survives",
      "type": "population_preserved",
      "baseline": "baseline",
      "evaluated": "evaluated",
      "key": "account_id"
    }
  ]
}
```

Reports can be emitted for people or automation:

```bash
metricproof audit examples/retention_contract.json --format json
metricproof audit examples/retention_contract.json \
  --format markdown --output audit-report.md
```

## Python API

```python
from metricproof import check_population_preserved

eligible = [{"account_id": "A01"}, {"account_id": "A02"}]
evaluated = [{"account_id": "A01"}]

result = check_population_preserved(
    eligible,
    evaluated,
    key="account_id",
)

assert result.status == "fail"
assert result.evidence == [
    {"key": "A02", "issue": "missing from evaluated population"}
]
```

Inputs are sequences of dictionaries, so the package works with standard CSV
and JSON data and can also accept records from a dataframe:

```python
rows = dataframe.to_dict(orient="records")
```

## What this demonstrates for a data-analysis portfolio

- Translating KPI definitions into testable business rules
- Retention and cohort-analysis methodology
- Denominator governance and survivorship-bias detection
- Cross-table reconciliation and analytical grain control
- Python package design, type hints, CLI design, and JSON contracts
- Automated tests, CI, machine-readable reporting, and documentation

Suggested CV bullet:

> Built MetricProof, a dependency-free Python analytics QA package that audits
> KPI formulas, cohort denominators, entity-population preservation, and
> cross-table reconciliation; shipped a JSON contract CLI, actionable evidence
> reports, automated tests, and multi-version CI.

## Design boundaries

MetricProof intentionally stays small:

- CSV and JSON are supported directly; warehouse connections are out of scope.
- Strict retention is expected to be monotonic. Set `"monotonic": false` for
  rolling or resurrection-style retention.
- The package validates supplied analytical outputs; it does not calculate
  product KPIs or replace source-system tests.
- This repository is an initial `0.1.0` portfolio release, not a claim of
  production maturity.

## Development

```bash
$env:PYTHONPATH = (Resolve-Path src).Path
python -m unittest discover -s tests -v
python -m metricproof audit examples/retention_contract.json
python -m metricproof audit examples/broken_retention_contract.json
```

On macOS or Linux, use `export PYTHONPATH="$PWD/src"` instead.

## License

MIT
