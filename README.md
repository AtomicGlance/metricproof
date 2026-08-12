# MetricProof

[![Tests](https://github.com/AtomicGlance/metricproof/actions/workflows/tests.yml/badge.svg)](https://github.com/AtomicGlance/metricproof/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/metricproof.svg)](https://pypi.org/project/metricproof/)
[![Python](https://img.shields.io/pypi/pyversions/metricproof.svg)](https://pypi.org/project/metricproof/)

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

The checks are deliberately narrow. They complement schema validation by
testing whether a published analytical result still matches its declared
population, grain, and calculation.

## Quick start

MetricProof requires Python 3.11 or newer and has no runtime dependencies.

```bash
python -m pip install metricproof
metricproof --help
metricproof --version
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
  "contract_version": "1.0",
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

JSON and Markdown reports also record a dataset inventory: the
contract-relative source path, row count, file size, and SHA-256 fingerprint.
This makes an audit reproducible and lets a reviewer confirm which exact
extracts produced the reported result, even when the source files are
regenerated later.

MetricProof 0.2 reports use a versioned, domain-neutral evidence envelope. The
JSON output includes `schema_version`, `report_type`, producer identity,
artifact fingerprints, structured check results, and report-specific context.
Print the bundled schemas or validate a contract before loading its data:

```bash
metricproof schema contract
metricproof schema evidence
metricproof validate-contract examples/retention_contract.json
```

## Check plugins

External packages can add contract check types without modifying MetricProof.
A runner receives the check definition, loaded datasets, and severity, and
returns a `CheckResult`:

```python
from metricproof import CheckResult, register_check_type

def row_count(check, datasets, severity):
    observed = len(datasets[check["dataset"]])
    expected = int(check["expected"])
    return CheckResult(
        check_id=check["id"],
        check_type="row_count",
        status="pass" if observed == expected else "fail",
        severity=severity,
        message=f"Observed {observed} row(s); expected {expected}.",
        observed=observed,
        expected=expected,
    )

register_check_type("row_count", row_count)
```

Published plugins should expose the runner through the
`metricproof.checks` entry-point group. The entry-point name becomes the
contract check type:

```toml
[project.entry-points."metricproof.checks"]
row_count = "my_package.checks:row_count"
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

## Where it fits

MetricProof is useful after analytical tables or dashboard extracts have been
produced and before their metrics are published. A JSON contract can run
locally, in a scheduled pipeline, or in CI and return a non-zero exit code when
a critical analytical assumption fails.

It does not replace source-system validation. Instead, it checks the layer
between clean source data and a trustworthy reported metric.

## Design boundaries

MetricProof intentionally stays small:

- CSV and JSON are supported directly; warehouse connections are out of scope.
- Strict retention is expected to be monotonic. Set `"monotonic": false` for
  rolling or resurrection-style retention.
- The package validates supplied analytical outputs; it does not calculate
  product KPIs or replace source-system tests.
- Version `0.2.0` introduces versioned contracts, external check plugins, and
  a stable evidence-report schema shared with domain integrations.

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
