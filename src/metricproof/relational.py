"""Checks for declared equality-join cardinality and grouped totals."""

from collections import Counter, defaultdict
from math import isclose, isfinite

from .checks import Rows, _number, _result


def _keys(rows, keys):
    if not isinstance(keys, (list, tuple)) or not keys or any(
        not isinstance(k, str) or not k for k in keys
    ) or len(set(keys)) != len(keys):
        raise ValueError("keys must be a nonempty sequence of distinct column names")
    result = []
    for row in rows:
        values = []
        for column in keys:
            if column not in row:
                raise ValueError(f"missing key column: {column}")
            value = row[column]
            if value is None or value == "":
                raise ValueError(f"missing key value in {column}; null keys are not supported")
            if type(value) not in (str, int, float) or (
                isinstance(value, float) and not isfinite(value)
            ):
                raise ValueError("keys must be finite numbers or nonempty strings")
            values.append(value)
        result.append(tuple(values))
    return result


def check_join_integrity(
    left_rows: Rows, right_rows: Rows, joined_rows: Rows, *, keys,
    relationship="many_to_one", join_type="left", missing_keys="error",
    check_id="join-integrity", severity="critical",
):
    """Check key multiplicities, not joined payload values or SQL execution.

    The same named keys must exist in all extracts. Null/blank keys are rejected.
    One-to-many relationships are outside this check's supported scope.
    """
    if relationship not in ("one_to_one", "many_to_one"):
        raise ValueError("relationship must be one_to_one or many_to_one")
    if join_type not in ("left", "inner"):
        raise ValueError("join_type must be left or inner")
    if missing_keys != "error":
        raise ValueError("only missing_keys='error' is supported")
    left, right, joined = (
        Counter(_keys(rows, keys)) for rows in (left_rows, right_rows, joined_rows)
    )
    evidence = []
    issues = 0

    def record(key, **details):
        nonlocal issues
        issues += 1
        if len(evidence) < 10:
            evidence.append({"key": dict(zip(keys, key)), **details})

    for side, counts in (("right", right), ("left", left)):
        if side == "left" and relationship == "many_to_one":
            continue
        for key, count in counts.items():
            if count > 1:
                record(key, issue="nonunique relationship key", side=side, rows=count)
    expected = {
        key: count for key, count in left.items()
        if join_type == "left" or key in right
    }
    # Insertion order is stable; no sorting of potentially mixed key types.
    for key in dict.fromkeys([*expected, *joined]):
        if expected.get(key, 0) != joined[key]:
            record(key, issue="joined multiplicity mismatch",
                   observed=joined[key], expected=expected.get(key, 0))
    return _result(
        issues == 0, check_id=check_id, check_type="join_integrity", severity=severity,
        pass_message="Join key multiplicities match the declared relationship.",
        fail_message=f"{issues} join integrity issue(s) found.",
        observed={"joined_rows": len(joined_rows), "issues": issues},
        expected={"joined_rows": sum(expected.values()), "relationship": relationship,
                  "join_type": join_type, "missing_keys": missing_keys},
        evidence=evidence,
        why_it_matters="A join can preserve every entity while multiplying its contribution.",
        suggested_fix="Check key uniqueness and join conditions before calculating metrics.",
    )


def check_grouped_reconciliation(
    left_rows: Rows, right_rows: Rows, *, keys, left_column, right_column,
    absolute_tolerance=0.0, relative_tolerance=0.0, missing_values="error",
    check_id="grouped-reconciliation", severity="critical",
):
    """Reconcile sums per group; missing groups fail even when their sum is zero."""
    for tolerance in (absolute_tolerance, relative_tolerance):
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or (
            not isfinite(tolerance) or tolerance < 0
        ):
            raise ValueError("tolerances must be finite nonnegative numbers")
    if missing_values not in ("error", "zero"):
        raise ValueError("missing_values must be error or zero")

    def totals(rows, column):
        values = defaultdict(float)
        for row, key in zip(rows, _keys(rows, keys)):
            if column not in row:
                raise ValueError(f"missing value column: {column}")
            raw = row[column]
            value = 0.0 if missing_values == "zero" and raw in (None, "") else _number(raw, column)
            if not isfinite(value):
                raise ValueError("group values must be finite")
            values[key] += value
            if not isfinite(values[key]):
                raise ValueError("group sum is not finite")
        return values

    left, right = totals(left_rows, left_column), totals(right_rows, right_column)
    evidence = []
    issues = 0
    for key in dict.fromkeys([*left, *right]):
        a, b = left.get(key), right.get(key)
        missing = a is None or b is None
        if missing or not isclose(a, b, abs_tol=absolute_tolerance, rel_tol=relative_tolerance):
            issues += 1
            if len(evidence) < 10:
                evidence.append({"key": dict(zip(keys, key)), "expected": a, "observed": b,
                                 "difference": None if missing else b - a,
                                 "issue": "missing group" if missing else "sum mismatch"})
    return _result(
        issues == 0, check_id=check_id, check_type="grouped_reconciliation", severity=severity,
        pass_message="All group sums reconcile.", fail_message=f"{issues} group(s) do not reconcile.",
        observed={"mismatched_groups": issues},
        expected={"absolute_tolerance": absolute_tolerance, "relative_tolerance": relative_tolerance,
                  "missing_values": missing_values}, evidence=evidence,
        why_it_matters="Opposite group errors can cancel out in a headline total.",
        suggested_fix="Inspect group filters, missing groups, and join multiplicities.",
    )
