import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from metricproof import (
    audit_contract,
    check_grouped_reconciliation,
    check_join_integrity,
    check_population_preserved,
)


class RelationalTests(unittest.TestCase):
    def test_participant_example(self):
        import runpy

        example = Path(__file__).resolve().parents[1] / "examples" / "participant_flow.py"
        results = runpy.run_path(str(example))["run"]()
        self.assertEqual([r.status for r in results],
                         ["pass", "fail", "fail", "fail", "pass", "fail", "pass"])

    def test_population_can_pass_inflated_join(self):
        left = [{"id": "a"}, {"id": "b"}]
        inflated = left + [left[0]]
        self.assertEqual(check_population_preserved(left, inflated, "id").status, "pass")
        self.assertEqual(check_join_integrity(left, inflated, inflated, keys=["id"]).status, "fail")
        self.assertEqual(check_join_integrity(left, left, left, keys=["id"]).status, "pass")

    def test_relationships_and_join_types(self):
        a, b = {"id": "a"}, {"id": "b"}
        for join_type, joined in (("left", [a, a, b]), ("inner", [a, a])):
            with self.subTest(join_type=join_type):
                result = check_join_integrity([a, a, b], [a], joined, keys=["id"], join_type=join_type)
                self.assertEqual(result.status, "pass")
                self.assertEqual(check_join_integrity([a, a, b], [a], joined, keys=["id"],
                                                     join_type=join_type, relationship="one_to_one").status, "fail")
        for joined in ([], [a, b, b], [a, {"id": "other"}]):
            self.assertEqual(check_join_integrity([a, b], [a], joined, keys=["id"]).status, "fail")

    def test_composite_empty_and_bad_keys(self):
        rows = [{"id": 1, "visit": "a"}, {"id": 1, "visit": "b"}]
        self.assertEqual(check_join_integrity(rows, rows, rows, keys=["id", "visit"], relationship="one_to_one").status, "pass")
        self.assertEqual(check_join_integrity([], [], [], keys=["id"]).status, "pass")
        for row in ({}, {"id": None}, {"id": ""}, {"id": []}, {"id": float("nan")}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                check_join_integrity([row], [], [], keys=["id"])
        for keys in ([], "id", ["id", "id"]):
            with self.assertRaises(ValueError):
                check_join_integrity([], [], [], keys=keys)
        for options in ({"relationship": "one_to_many"}, {"join_type": "outer"}, {"missing_keys": "match"}):
            with self.assertRaises(ValueError):
                check_join_integrity([], [], [], keys=["id"], **options)

    def test_bounded_evidence(self):
        rows = [{"id": i} for i in range(25)]
        result = check_join_integrity(rows, rows, [], keys=["id"])
        self.assertEqual(result.observed["issues"], 25)
        self.assertEqual(len(result.evidence), 10)

    def grouped(self, left, right, **kwargs):
        return check_grouped_reconciliation(left, right, keys=["g"], left_column="v", right_column="v", **kwargs)

    def test_cancelling_errors(self):
        left = [{"g": "a", "v": 1000}, {"g": "b", "v": 1000}]
        right = [{"g": "a", "v": 1500}, {"g": "b", "v": 500}]
        self.assertEqual(self.grouped(left, right).observed["mismatched_groups"], 2)
        self.assertEqual(self.grouped(left, left).status, "pass")

    def test_group_boundaries(self):
        self.assertEqual(self.grouped([], []).status, "pass")
        self.assertEqual(self.grouped([{"g": "a", "v": 0}], []).status, "fail")
        a, b = [{"g": "a", "v": 100}], [{"g": "a", "v": 101}]
        self.assertEqual(self.grouped(a, b, absolute_tolerance=1).status, "pass")
        self.assertEqual(self.grouped(a, b, relative_tolerance=0.01).status, "pass")
        for value in (None, "", "oops", float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                self.grouped([{"g": "a", "v": value}], b)
        self.assertEqual(self.grouped([{"g": "a", "v": None}], [{"g": "a", "v": 0}], missing_values="zero").status, "pass")
        for tolerance in (-1, float("nan"), float("inf"), "1", True):
            with self.assertRaises(ValueError):
                self.grouped(a, b, absolute_tolerance=tolerance)

    def test_contract_dispatch(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rows.json").write_text(json.dumps([{"id": "a", "v": 1}]))
            contract = {"contract_version": "1.0", "datasets": {"a": "rows.json"}, "checks": [
                {"id": "join", "type": "join_integrity", "left": "a", "right": "a", "joined": "a", "keys": ["id"]},
                {"id": "groups", "type": "grouped_reconciliation", "left": {"dataset": "a", "column": "v"}, "right": {"dataset": "a", "column": "v"}, "keys": ["id"]},
            ]}
            path = root / "contract.json"
            path.write_text(json.dumps(contract))
            self.assertEqual([r.status for r in audit_contract(path).results], ["pass", "pass"])
            contract["checks"][0]["relationship"] = "unsupported"
            path.write_text(json.dumps(contract))
            self.assertEqual(audit_contract(path).results[0].status, "error")
