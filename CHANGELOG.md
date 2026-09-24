# Changelog

## 0.4.0

- Add `join_integrity` to check key multiplicities for one-to-one and many-to-one
  left/inner equality joins, including composite keys and bounded evidence.
- Add `grouped_reconciliation` to detect offsetting group errors, missing groups,
  and differences exceeding explicit absolute/relative tolerances.
- Expose both checks through JSON contracts and the Python API without changing
  existing reconciliation semantics or the evidence schema.
- Add a synthetic participant-flow example covering exclusions, unexplained
  loss, duplicate participants, group imbalance, and inflated joins.
- Document unsupported joins, missing-value policies, floating-point arithmetic,
  and the limits of key-level checks and scientific interpretation.

## 0.3.0

- Compare saved metric audits with `compare_reports()` or `metricproof compare`.
- Distinguish new regressions, persistent failures, removed checks, changed
  definitions, runner changes, and input changes.
- Record check configuration fingerprints and runner identities in evidence v1's
  extensible context. Legacy v1 reports remain readable with explicit uncertainty.
- Add a reproducible retention example demonstrating a relaxed rule hiding loss.
