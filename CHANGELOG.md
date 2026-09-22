# Changelog

## 0.3.0

- Compare saved metric audits with `compare_reports()` or `metricproof compare`.
- Distinguish new regressions, persistent failures, removed checks, changed
  definitions, runner changes, and input changes.
- Record check configuration fingerprints and runner identities in evidence v1's
  extensible context. Legacy v1 reports remain readable with explicit uncertainty.
- Add a reproducible retention example demonstrating a relaxed rule hiding loss.
