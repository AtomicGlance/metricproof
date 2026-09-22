"""Generate three reproducible audits showing population loss and a relaxed rule.

Run from the repository root: python examples/compare_retention.py
Outputs go to examples/comparison-output (ignored by Git).
"""

import json
from pathlib import Path

from metricproof import audit_contract, compare_reports
from metricproof.comparison import render_comparison


def main():
    root = Path(__file__).resolve().parent / "comparison-output"
    root.mkdir(exist_ok=True)
    rows = [{"account_id": "A"}, {"account_id": "B"}]
    (root / "baseline.json").write_text(json.dumps(rows), encoding="utf-8")
    contract = {
        "title": "Retention population evidence",
        "contract_version": "1.0",
        "datasets": {"baseline": "baseline.json", "evaluated": "evaluated.json"},
        "checks": [
            {
                "id": "eligible-population",
                "type": "population_preserved",
                "baseline": "baseline",
                "evaluated": "evaluated",
                "key": "account_id",
                "minimum_coverage": 1.0,
            }
        ],
    }
    reports = []
    for name, evaluated, coverage in (
        ("initial", rows, 1.0),
        ("dropped", rows[:1], 1.0),
        ("relaxed", rows[:1], 0.5),
    ):
        (root / "evaluated.json").write_text(json.dumps(evaluated), encoding="utf-8")
        contract["checks"][0]["minimum_coverage"] = coverage
        path = root / "contract.json"
        path.write_text(json.dumps(contract), encoding="utf-8")
        report = audit_contract(path).to_dict()
        # Fixed display timestamp; actual input/definition hashes are retained.
        report["generated_at"] = "2026-01-01T00:00:00+00:00"
        (root / f"{name}.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        reports.append(report)
    for old, new in zip(reports, reports[1:]):
        print(render_comparison(compare_reports(old, new)))


if __name__ == "__main__":
    main()
