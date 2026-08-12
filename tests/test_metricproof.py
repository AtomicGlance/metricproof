from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from metricproof import (
    CheckResult,
    audit_contract,
    check_cohort_integrity,
    check_population_preserved,
    check_ratio_consistency,
    check_unique_grain,
    register_check_type,
)
from metricproof.contract import load_contract
from metricproof.plugins import unregister_check_type
from metricproof.report import render_json, render_markdown
from metricproof.schema import load_schema


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
        markdown = render_markdown(report)
        self.assertIn("survivorship bias", markdown)
        self.assertIn("—", markdown)
        self.assertNotIn("â€”", markdown)

    def test_json_report_is_machine_readable(self):
        report = audit_contract(ROOT / "examples" / "retention_contract.json")
        payload = json.loads(render_json(report))
        self.assertTrue(payload["passed"])
        self.assertEqual(len(payload["results"]), 6)

        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["report_type"], "metric-audit")
        self.assertEqual(payload["producer"]["name"], "metricproof")
        self.assertEqual(payload["producer"]["version"], "0.2.0")
        headline = next(
            artifact for artifact in payload["artifacts"]
            if artifact["name"] == "headline"
        )
        self.assertEqual(headline["uri"], "data/headline.csv")
        self.assertEqual(headline["metadata"]["rows"], report.datasets["headline"])
        self.assertEqual(len(headline["sha256"]), 64)
        self.assertTrue(all(char in "0123456789abcdef" for char in headline["sha256"]))
        markdown = render_markdown(report)
        self.assertIn("| Dataset | Source | Rows | SHA-256 |", markdown)
        self.assertIn(headline["sha256"], markdown)

    def test_contract_and_evidence_schemas_are_bundled(self):
        contract_schema = load_schema("contract")
        evidence_schema = load_schema("evidence")
        Draft202012Validator.check_schema(contract_schema)
        Draft202012Validator.check_schema(evidence_schema)
        self.assertEqual(contract_schema["properties"]["contract_version"]["const"], "1.0")
        self.assertEqual(evidence_schema["properties"]["schema_version"]["const"], "1.0")

        contract = json.loads(
            (ROOT / "examples" / "retention_contract.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(contract_schema).validate(contract)
        report = audit_contract(ROOT / "examples" / "retention_contract.json")
        Draft202012Validator(evidence_schema).validate(report.to_dict())

    def test_contract_version_is_required_and_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text('{"datasets": {"data": "data.csv"}, "checks": []}')
            with self.assertRaisesRegex(ValueError, "contract_version"):
                load_contract(path)

            path.write_text(
                '{"contract_version": "2.0", "datasets": {"data": "data.csv"}, "checks": []}'
            )
            with self.assertRaisesRegex(ValueError, "unsupported contract_version"):
                load_contract(path)

    def test_duplicate_check_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps({
                "contract_version": "1.0",
                "datasets": {"data": "data.csv"},
                "checks": [
                    {"id": "duplicate", "type": "one"},
                    {"id": "duplicate", "type": "two"},
                ],
            }))
            with self.assertRaisesRegex(ValueError, "duplicate check id"):
                load_contract(path)

    def test_registered_plugin_check_runs_from_contract(self):
        def always_passes(check, datasets, severity):
            return CheckResult(
                check_id=check["id"],
                check_type="always_passes",
                status="pass",
                severity=severity,
                message=f"Plugin inspected {len(datasets[check['dataset']])} row(s).",
            )

        register_check_type("always_passes", always_passes)
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data.csv").write_text("id\n1\n", encoding="utf-8")
                contract = root / "contract.json"
                contract.write_text(json.dumps({
                    "contract_version": "1.0",
                    "datasets": {"data": "data.csv"},
                    "checks": [
                        {"id": "external-check", "type": "always_passes", "dataset": "data"}
                    ],
                }), encoding="utf-8")
                report = audit_contract(contract)
                self.assertTrue(report.passed)
                self.assertEqual(report.results[0].message, "Plugin inspected 1 row(s).")
        finally:
            unregister_check_type("always_passes")

    def test_dataset_fingerprint_is_stable(self):
        contract = ROOT / "examples" / "retention_contract.json"
        first = audit_contract(contract).dataset_metadata
        second = audit_contract(contract).dataset_metadata
        self.assertEqual(first, second)

    def test_report_generation_timestamp_is_stable(self):
        report = audit_contract(ROOT / "examples" / "retention_contract.json")
        first = report.to_dict()["generated_at"]
        second = report.to_dict()["generated_at"]
        self.assertEqual(first, second)

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
        self.assertEqual(result.stdout, "metricproof 0.2.0\n")
        self.assertEqual(result.stderr, "")

    def test_cli_validates_contract_without_loading_datasets(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "metricproof",
                "validate-contract",
                str(ROOT / "examples" / "retention_contract.json"),
            ],
            env={"PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Valid MetricProof contract 1.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
