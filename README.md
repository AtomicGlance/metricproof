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

## Compare saved audits (0.3)

Save audit JSON before and after a data or contract change, then compare:

```bash
metricproof compare previous.json current.json
metricproof compare previous.json current.json --format markdown --output changes.md
metricproof compare previous.json current.json --format json
```

The Python API is `compare_reports(previous_report, current_report)`, accepting
decoded report dictionaries or MetricProof report objects. It reads no datasets
and executes no plugins. Results expose `changes`, `warnings`, `regressions`,
`current_failures`, `needs_review`, `exit_code`, and `to_dict()`.

Checks are matched by `check_id`, artifacts by `name`; duplicates are errors.
Timestamps and result/artifact ordering are ignored. Configuration arrays retain
their order because order can affect a plugin's meaning. Definition fingerprints
use sorted-key compact JSON with non-finite numbers prohibited. An explicit
default option and an omitted option may be flagged as different conservatively.

Audit reports now record each definition and its SHA-256 fingerprint under
`context.contract.checks`, together with runner identity/version. This is an
additive use of evidence schema 1.0's open context; existing consumers and older
reports remain supported. Registered custom runners without distribution metadata
have an unknown version. Entry-point plugins record their distribution version.

Comparison exit codes:

- `0`: no new blocking result or review requirement. An unchanged existing audit
  failure remains visible under `current_failures`; this is not a clean-audit gate.
- `1`: a new critical failure/error, escalation to an execution error, removed
  critical check, changed definition/type/severity/runner/producer/contract version,
  or unknown comparability requires attention.
- `2`: malformed input, contradictory summaries, duplicate identifiers, unsupported
  schema/report type, or a file I/O error.

Input fingerprints changing alone do not block. Removed checks are reported as
removed, never as improvements. Old reports missing definition provenance require
review. Changed observed/expected values are shown without automatically blocking.
Only `metric-audit` reports are supported; NWB evidence semantics need a separate
adapter. Fingerprints detect differences, not authenticity or scientific validity.

For CI, run the current audit and comparison as separate steps so existing audit
failures still block. Preserve the baseline from a trusted previous build, rather
than replacing it automatically with the new output:

```yaml
- run: metricproof audit contract.json --format json --output current.json
- if: always()
  run: metricproof compare baseline.json current.json --format markdown --output changes.md
```

Reproduce population loss followed by a relaxed contract:

```bash
python examples/compare_retention.py
metricproof compare examples/comparison-output/initial.json examples/comparison-output/dropped.json
metricproof compare examples/comparison-output/dropped.json examples/comparison-output/relaxed.json
```

Both comparisons exit 1: the first loses half the eligible accounts; the second
changes the minimum coverage to 50%, causing the audit to pass but requiring review
of the changed definition. The script writes three saved audits and rebuilds its
small synthetic inputs; it overwrites only its generated `comparison-output`
directory files. These demonstrate recorded evidence, not a claim about real
customer behavior or the appropriateness of a 50% threshold.

## Join integrity and grouped reconciliation

Two additional built-in checks audit relationships between extracts. Existing
`reconciliation` behavior is unchanged. Both work through the Python API and
JSON contracts:

```json
{"id": "customer-join", "type": "join_integrity",
 "left": "customers", "right": "subscriptions", "joined": "joined",
 "keys": ["customer_id"], "relationship": "many_to_one",
 "join_type": "left", "missing_keys": "error"}
```

Dataset names refer to the contract's `datasets` mapping. Keys must have the same
names in all three extracts; composite keys are supported. `one_to_one` requires
both input keys to be unique; `many_to_one` requires the right keys to be unique.
`left` preserves left multiplicities, while `inner` retains only matching keys.
Duplicate right keys fail even when the joined extract has been deduplicated.
One-to-many and outer joins are unsupported, not evidence of incorrect data.
Blank/null keys are errors; key types are not coerced (CSV strings and JSON
numbers should be normalized consistently before auditing). Empty extracts are
allowed. The check verifies key multiplicities, **not non-key payload values**,
the actual SQL, or the appropriateness of the declared relationship.

```json
{"id": "regional-totals", "type": "grouped_reconciliation",
 "left": {"dataset": "expected", "column": "amount"},
 "right": {"dataset": "reported", "column": "amount"},
 "keys": ["region"], "absolute_tolerance": 0.01,
 "relative_tolerance": 0.0, "missing_values": "error"}
```

This compares sums per group. A missing group fails even if its sum would be
zero. Tolerances are finite and nonnegative; a group passes when its absolute
difference is at most the larger of the absolute tolerance and the relative
tolerance multiplied by the larger absolute total. Missing numeric values
default to errors; explicit `missing_values: "zero"` treats blanks/nulls as zero,
but never missing columns or non-finite numbers. Arithmetic uses floating point,
not exact monetary decimals. Evidence contains at most ten issues, with total
issue counts retained in the summary. Samples may contain sensitive identifiers;
review reports before sharing them.

Run the synthetic research example:

```bash
python examples/participant_flow.py
```

It accounts for one screening exclusion, detects an unexplained participant loss,
flags a duplicate participant, and exposes a treatment-group loss despite an
unchanged total row count. It also demonstrates population preservation passing
an inflated join while join integrity fails, followed by a valid join passing.
It does not assess exclusion validity, statistical significance, causality, or
whether the supplied extracts represent the complete study.

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
