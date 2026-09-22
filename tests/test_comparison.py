"""Behavioral regressions for offline evidence comparison."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from metricproof import audit_contract, compare_reports
from metricproof.cli import main
from metricproof.comparison import definition_digest, render_comparison

ROOT = Path(__file__).resolve().parents[1]


def summary(report):
    report["counts"] = {
        s: sum(c["status"] == s for c in report["results"])
        for s in ("pass", "fail", "error")
    }
    report["passed"] = not any(
        c["status"] == "error"
        or (c["status"] == "fail" and c["severity"] == "critical")
        for c in report["results"]
    )


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.old = audit_contract(ROOT / "examples/retention_contract.json").to_dict()
        self.new = copy.deepcopy(self.old)

    def test_identical_and_ordering(self):
        self.new["generated_at"] = "2026-01-01T00:00:00Z"
        self.new["results"].reverse()
        self.new["artifacts"].reverse()
        result = compare_reports(self.old, self.new)
        self.assertEqual(result.changes, [])
        self.assertEqual(result.exit_code, 0)

    def test_all_status_transitions(self):
        for before in ("pass", "fail", "error"):
            for after in ("pass", "fail", "error"):
                with self.subTest(before=before, after=after):
                    self.old["results"][0]["status"] = before
                    self.new["results"][0]["status"] = after
                    summary(self.old)
                    summary(self.new)
                    result = compare_reports(self.old, self.new)
                    expected = (before == "pass" and after != "pass") or (
                        before == "fail" and after == "error"
                    )
                    self.assertEqual(bool(result.regressions), expected)
                    self.assertEqual(bool(result.current_failures), after != "pass")

    def test_removed_critical_check_blocks(self):
        removed = self.new["results"].pop()
        del self.new["context"]["contract"]["checks"][removed["check_id"]]
        summary(self.new)
        self.assertEqual(compare_reports(self.old, self.new).exit_code, 1)

    def test_added_failure_blocks(self):
        removed = self.old["results"].pop()
        del self.old["context"]["contract"]["checks"][removed["check_id"]]
        self.new["results"][-1]["status"] = "fail"
        summary(self.old)
        summary(self.new)
        self.assertTrue(compare_reports(self.old, self.new).regressions)

    def test_changed_input_does_not_block(self):
        self.new["artifacts"][0]["sha256"] = "0" * 64
        result = compare_reports(self.old, self.new)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.changes[0]["field"], "sha256")

    def test_legacy_unknown(self):
        del self.old["context"]["contract"]["checks"]
        result = compare_reports(self.old, self.new)
        self.assertTrue(result.warnings)
        self.assertTrue(result.needs_review)

    def test_invalid_inputs(self):
        for field, value in (
            ("schema_version", "2.0"),
            ("report_type", "nwb"),
            ("results", None),
            ("passed", False),
        ):
            with self.subTest(field=field):
                bad = dict(self.old, **{field: value})
                with self.assertRaises(ValueError):
                    compare_reports(bad, self.new)
        for field in ("results", "artifacts"):
            bad = copy.deepcopy(self.old)
            bad[field].append(bad[field][0])
            with self.assertRaisesRegex(ValueError, "duplicate"):
                compare_reports(bad, self.new)

    def test_definition_digest_and_plugin_unknown(self):
        self.assertEqual(
            definition_digest({"a": 1, "b": 2}), definition_digest({"b": 2, "a": 1})
        )
        item = next(iter(self.new["context"]["contract"]["checks"].values()))
        item["runner"]["version"] = None
        self.assertTrue(compare_reports(self.old, self.new).warnings)
        item["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            compare_reports(self.old, self.new)

    def test_loosened_threshold_is_not_improvement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "rows.json").write_text('[{"x": 12}]')
            contract = {
                "contract_version": "1.0",
                "datasets": {"data": "rows.json"},
                "checks": [
                    {
                        "id": "limit",
                        "type": "numeric_range",
                        "dataset": "data",
                        "column": "x",
                        "maximum": 10,
                    }
                ],
            }
            path = root / "contract.json"
            path.write_text(json.dumps(contract))
            old = audit_contract(path)
            contract["checks"][0]["maximum"] = 20
            path.write_text(json.dumps(contract))
            new = audit_contract(path)
            self.assertFalse(old.passed)
            self.assertTrue(new.passed)
            result = compare_reports(old, new)
            self.assertEqual(result.exit_code, 1)
            self.assertTrue(any(c["field"] == "definition" for c in result.changes))

    def test_cli_formats_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps(self.old))
            for format in ("text", "json", "markdown"):
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(
                        main(["compare", str(path), str(path), "--format", format]), 0
                    )
                self.assertTrue(output.getvalue())
            path.write_text("{}")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["compare", str(path), str(path)]), 2)
        rendered = render_comparison(compare_reports(self.old, self.new), "json")
        self.assertTrue(json.loads(rendered)["policy_passed"])

    def test_versions_and_severity(self):
        self.new["producer"]["version"] = "999"
        self.assertTrue(compare_reports(self.old, self.new).needs_review)
        self.new = copy.deepcopy(self.old)
        self.new["results"][0]["severity"] = "warning"
        self.assertTrue(compare_reports(self.old, self.new).needs_review)

    def test_provenance_remains_evidence_v1_compatible(self):
        import jsonschema

        from metricproof.schema import load_schema

        jsonschema.validate(self.new, load_schema("evidence"))
        del self.old["context"]["contract"]["checks"]
        jsonschema.validate(self.old, load_schema("evidence"))

    def test_observed_expected_and_artifact_membership(self):
        self.new["results"][0]["observed"] = 999
        self.new["results"][0]["expected"] = 1000
        self.new["artifacts"].pop()
        result = compare_reports(self.old, self.new)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            {c["field"] for c in result.changes}, {"observed", "expected", "removed"}
        )

    def test_nonfinite_and_bad_status_rejected(self):
        self.new["results"][0]["observed"] = float("nan")
        with self.assertRaises(ValueError):
            compare_reports(self.old, self.new)
        self.new = copy.deepcopy(self.old)
        self.new["results"][0]["status"] = "maybe"
        with self.assertRaises(ValueError):
            compare_reports(self.old, self.new)

    def test_runner_replacement_has_unknown_version(self):
        from metricproof.plugins import (
            check_identity,
            register_check_type,
            unregister_check_type,
        )

        def runner(check, datasets, severity):
            raise AssertionError("comparison must not execute runners")

        register_check_type("comparison-test", runner)
        try:
            self.assertIsNone(check_identity("comparison-test")["version"])
            self.assertEqual(compare_reports(self.old, self.new).exit_code, 0)
        finally:
            unregister_check_type("comparison-test")
