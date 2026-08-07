from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from metricproof import (
    audit_contract,
    check_cohort_integrity,
    check_population_preserved,
    check_ratio_consistency,
    check_unique_grain,
)
from metricproof.report import render_json, render_markdown


ROOT = Path(__file__).resolve().parents[1]


class CheckTests(unittest.TestCase):
    def test_unique_grain_detects_duplicate_key(self):
        rows = [{"month": "Jan"}, {"month": "Jan"}]
        result = check_unique_grain(rows, ["month"])
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.observed["extra_rows"], 1)

    def test_ratio_detects_denominator_mismatch(self):
        rows = [{"won": "3", "eligible": "4", "rate": "0.5"}]
        result = check_ratio_consistency(rows, "won", "eligible", "rate")
        self.assertEqual(result.status, "fail")
        self.assertAlmostEqual(result.evidence[0]["computed_rate"], 0.75)

    def test_population_check_exposes_survivorship_bias(self):
        baseline = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        evaluated = [{"id": "A"}, {"id": "B"}]
        result = check_population_preserved(baseline, evaluated, "id")
        self.assertEqual(result.status, "fail")
        self.assertAlmostEqual(result.observed["coverage"], 2 / 3)
        self.assertEqual(result.evidence[0]["key"], "C")

    def test_cohort_check_detects_growth_in_strict_retention(self):
        rows = [
            {"cohort": "Jan", "period": 0, "size": 3, "retained": 3, "rate": 1},
            {"cohort": "Jan", "period": 1, "size": 3, "retained": 2, "rate": 2 / 3},
            {"cohort": "Jan", "period": 2, "size": 3, "retained": 3, "rate": 1},
        ]
        result = check_cohort_integrity(
            rows,
            cohort="cohort",
            period="period",
            size="size",
            retained="retained",
            rate="rate",
        )
        self.assertEqual(result.status, "fail")
        self.assertTrue(
            any("increases" in item["issue"] for item in result.evidence)
        )


class ContractTests(unittest.TestCase):
    def test_valid_retention_contract_passes(self):
        report = audit_contract(ROOT / "examples" / "retention_contract.json")
        self.assertTrue(report.passed)
        self.assertEqual(report.counts, {"pass": 6, "fail": 0, "error": 0})

    def test_broken_contract_returns_actionable_failures(self):
        report = audit_contract(
            ROOT / "examples" / "broken_retention_contract.json"
        )
        self.assertFalse(report.passed)
        self.assertEqual(report.counts, {"pass": 0, "fail": 4, "error": 0})
        self.assertIn("survivorship bias", render_markdown(report))

    def test_json_report_is_machine_readable(self):
        report = audit_contract(ROOT / "examples" / "retention_contract.json")
        payload = json.loads(render_json(report))
        self.assertTrue(payload["passed"])
        self.assertEqual(len(payload["results"]), 6)

    def test_cli_exit_codes(self):
        environment = {"PYTHONPATH": str(ROOT / "src")}
        passing = subprocess.run(
            [
                sys.executable,
                "-m",
                "metricproof",
                "audit",
                str(ROOT / "examples" / "retention_contract.json"),
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        failing = subprocess.run(
            [
                sys.executable,
                "-m",
                "metricproof",
                "audit",
                str(ROOT / "examples" / "broken_retention_contract.json"),
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(passing.returncode, 0)
        self.assertEqual(failing.returncode, 1)
        self.assertIn("Result: FAIL", failing.stdout)

    def test_cli_version(self):
        result = subprocess.run(
            [sys.executable, "-m", "metricproof", "--version"],
            env={"PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "metricproof 0.1.0\n")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
