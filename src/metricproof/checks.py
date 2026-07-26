"""Small, dependency-free checks for common analytical failure modes."""

from __future__ import annotations

from collections import Counter, defaultdict
from math import isclose
from typing import Any, Iterable, Mapping, Sequence

from .models import CheckResult

Rows = Sequence[Mapping[str, Any]]


def _result(
    passed: bool,
    *,
    check_id: str,
    check_type: str,
    severity: str,
    pass_message: str,
    fail_message: str,
    observed: Any,
    expected: Any,
    evidence: list[dict[str, Any]],
    why_it_matters: str,
    suggested_fix: str,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        check_type=check_type,
        status="pass" if passed else "fail",
        severity=severity,
        message=pass_message if passed else fail_message,
        observed=observed,
        expected=expected,
        evidence=evidence[:10],
        why_it_matters=why_it_matters,
        suggested_fix="" if passed else suggested_fix,
    )


def _missing_columns(rows: Rows, columns: Iterable[str]) -> list[str]:
    available = set().union(*(row.keys() for row in rows)) if rows else set()
    return sorted(set(columns) - available)


def _number(value: Any, column: str) -> float:
    if value is None or value == "":
        raise ValueError(f"column '{column}' contains a blank numeric value")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"column '{column}' contains non-numeric value {value!r}"
        ) from exc


def check_unique_grain(
    rows: Rows,
    columns: Sequence[str],
    *,
    check_id: str = "unique-grain",
    severity: str = "critical",
) -> CheckResult:
    """Assert that a declared analytical grain uniquely identifies every row."""

    missing = _missing_columns(rows, columns)
    if missing:
        raise ValueError(f"missing columns: {', '.join(missing)}")

    keys = [tuple(row[column] for column in columns) for row in rows]
    counts = Counter(keys)
    duplicates = [
        {"key": dict(zip(columns, key)), "row_count": count}
        for key, count in counts.items()
        if count > 1
    ]
    duplicate_rows = sum(item["row_count"] - 1 for item in duplicates)
    return _result(
        not duplicates,
        check_id=check_id,
        check_type="unique_grain",
        severity=severity,
        pass_message=f"{len(rows)} rows match the declared grain.",
        fail_message=f"{duplicate_rows} extra row(s) violate the declared grain.",
        observed={"duplicate_keys": len(duplicates), "extra_rows": duplicate_rows},
        expected={"duplicate_keys": 0, "columns": list(columns)},
        evidence=duplicates,
        why_it_matters=(
            "Duplicate grain silently double-counts customers, revenue, or events."
        ),
        suggested_fix=(
            "Deduplicate upstream or add the missing dimension to the declared grain."
        ),
    )


def check_numeric_range(
    rows: Rows,
    column: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    check_id: str = "numeric-range",
    severity: str = "critical",
) -> CheckResult:
    """Assert that every numeric value lies inside an inclusive range."""

    missing = _missing_columns(rows, [column])
    if missing:
        raise ValueError(f"missing column: {column}")

    violations: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        value = _number(row[column], column)
        if (minimum is not None and value < minimum) or (
            maximum is not None and value > maximum
        ):
            violations.append({"row": index, "value": value})
    return _result(
        not violations,
        check_id=check_id,
        check_type="numeric_range",
        severity=severity,
        pass_message=f"All {len(rows)} '{column}' values are within range.",
        fail_message=f"{len(violations)} '{column}' value(s) are outside range.",
        observed={"violations": len(violations)},
        expected={"minimum": minimum, "maximum": maximum},
        evidence=violations,
        why_it_matters="Out-of-range metrics often signal unit, join, or denominator errors.",
        suggested_fix=(
            "Confirm the metric unit and inspect the rows shown in the evidence."
        ),
    )


def check_ratio_consistency(
    rows: Rows,
    numerator: str,
    denominator: str,
    rate: str,
    *,
    tolerance: float = 0.0001,
    check_id: str = "ratio-consistency",
    severity: str = "critical",
) -> CheckResult:
    """Recompute a reported rate from its numerator and denominator."""

    missing = _missing_columns(rows, [numerator, denominator, rate])
    if missing:
        raise ValueError(f"missing columns: {', '.join(missing)}")

    violations: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        num = _number(row[numerator], numerator)
        den = _number(row[denominator], denominator)
        reported = _number(row[rate], rate)
        if den <= 0:
            violations.append(
                {
                    "row": index,
                    "numerator": num,
                    "denominator": den,
                    "reported_rate": reported,
                    "reason": "denominator must be positive",
                }
            )
            continue
        computed = num / den
        if not isclose(reported, computed, abs_tol=tolerance, rel_tol=0.0):
            violations.append(
                {
                    "row": index,
                    "numerator": num,
                    "denominator": den,
                    "reported_rate": reported,
                    "computed_rate": round(computed, 8),
                    "difference": round(abs(reported - computed), 8),
                }
            )
    return _result(
        not violations,
        check_id=check_id,
        check_type="ratio_consistency",
        severity=severity,
        pass_message=f"All {len(rows)} reported rates recompute correctly.",
        fail_message=f"{len(violations)} reported rate(s) do not match their components.",
        observed={"violations": len(violations)},
        expected={"formula": f"{numerator} / {denominator}", "tolerance": tolerance},
        evidence=violations,
        why_it_matters=(
            "A plausible percentage can still be wrong when its denominator changed."
        ),
        suggested_fix=(
            "Recompute the rate from the audited numerator and denominator at the same grain."
        ),
    )


def _aggregate(rows: Rows, column: str, operation: str) -> float:
    if operation == "count":
        return float(len(rows))
    if operation == "distinct_count":
        return float(len({row[column] for row in rows}))
    values = [_number(row[column], column) for row in rows]
    if operation == "sum":
        return sum(values)
    raise ValueError(f"unsupported aggregate: {operation}")


def check_reconciliation(
    left_rows: Rows,
    right_rows: Rows,
    *,
    left_column: str,
    right_column: str,
    aggregate: str = "sum",
    tolerance: float = 0.0,
    check_id: str = "reconciliation",
    severity: str = "critical",
) -> CheckResult:
    """Reconcile an aggregate across two analytical tables."""

    if aggregate != "count":
        left_missing = _missing_columns(left_rows, [left_column])
        right_missing = _missing_columns(right_rows, [right_column])
        if left_missing or right_missing:
            raise ValueError(
                "missing reconciliation columns: "
                + ", ".join(left_missing + right_missing)
            )

    left_value = _aggregate(left_rows, left_column, aggregate)
    right_value = _aggregate(right_rows, right_column, aggregate)
    difference = abs(left_value - right_value)
    scale = max(abs(left_value), abs(right_value), 1.0)
    relative_difference = difference / scale
    passed = relative_difference <= tolerance
    evidence = [] if passed else [
        {
            "left": left_value,
            "right": right_value,
            "absolute_difference": difference,
            "relative_difference": round(relative_difference, 8),
        }
    ]
    return _result(
        passed,
        check_id=check_id,
        check_type="reconciliation",
        severity=severity,
        pass_message=f"The two {aggregate} aggregates reconcile.",
        fail_message=(
            f"The two {aggregate} aggregates differ by {relative_difference:.2%}."
        ),
        observed={
            "left": left_value,
            "right": right_value,
            "relative_difference": relative_difference,
        },
        expected={"maximum_relative_difference": tolerance},
        evidence=evidence,
        why_it_matters=(
            "Dashboard totals should tie back to their source or segment breakdown."
        ),
        suggested_fix=(
            "Compare filters, date cutoffs, join cardinality, and metric definitions."
        ),
    )


def check_population_preserved(
    baseline_rows: Rows,
    evaluated_rows: Rows,
    key: str,
    *,
    minimum_coverage: float = 1.0,
    allow_unexpected: bool = False,
    check_id: str = "population-preserved",
    severity: str = "critical",
) -> CheckResult:
    """Detect entities silently lost before a metric is calculated."""

    if _missing_columns(baseline_rows, [key]) or _missing_columns(evaluated_rows, [key]):
        raise ValueError(f"both datasets must contain key column '{key}'")
    baseline = {str(row[key]) for row in baseline_rows}
    evaluated = {str(row[key]) for row in evaluated_rows}
    missing = sorted(baseline - evaluated)
    unexpected = sorted(evaluated - baseline)
    coverage = 1.0 if not baseline else len(baseline & evaluated) / len(baseline)
    passed = coverage >= minimum_coverage and (allow_unexpected or not unexpected)
    evidence = [
        *({"key": item, "issue": "missing from evaluated population"} for item in missing),
        *({"key": item, "issue": "not present in baseline population"} for item in unexpected),
    ]
    return _result(
        passed,
        check_id=check_id,
        check_type="population_preserved",
        severity=severity,
        pass_message=(
            f"Evaluated population preserves {coverage:.1%} of baseline entities."
        ),
        fail_message=(
            f"Evaluated population preserves {coverage:.1%}; "
            f"{len(missing)} missing and {len(unexpected)} unexpected."
        ),
        observed={
            "coverage": coverage,
            "missing": len(missing),
            "unexpected": len(unexpected),
        },
        expected={
            "minimum_coverage": minimum_coverage,
            "unexpected_entities_allowed": allow_unexpected,
        },
        evidence=evidence,
        why_it_matters=(
            "Dropped inactive or unmatched entities create survivorship bias and inflate KPIs."
        ),
        suggested_fix=(
            "Start from the eligible baseline population and left join activity onto it."
        ),
    )


def check_cohort_integrity(
    rows: Rows,
    *,
    cohort: str,
    period: str,
    retained: str,
    size: str,
    rate: str,
    monotonic: bool = True,
    tolerance: float = 0.0001,
    check_id: str = "cohort-integrity",
    severity: str = "critical",
) -> CheckResult:
    """Validate cohort denominators, rates, period zero, and retention shape."""

    required = [cohort, period, retained, size, rate]
    missing = _missing_columns(rows, required)
    if missing:
        raise ValueError(f"missing columns: {', '.join(missing)}")

    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[cohort])].append(row)

    violations: list[dict[str, Any]] = []
    for cohort_value, group in groups.items():
        ordered = sorted(group, key=lambda row: _number(row[period], period))
        sizes = {_number(row[size], size) for row in ordered}
        if len(sizes) != 1:
            violations.append(
                {
                    "cohort": cohort_value,
                    "issue": "cohort size changes across periods",
                    "values": sorted(sizes),
                }
            )
        previous_retained: float | None = None
        has_period_zero = False
        for row in ordered:
            period_value = _number(row[period], period)
            retained_value = _number(row[retained], retained)
            size_value = _number(row[size], size)
            rate_value = _number(row[rate], rate)
            if size_value <= 0:
                violations.append(
                    {"cohort": cohort_value, "period": period_value, "issue": "non-positive cohort size"}
                )
                continue
            expected_rate = retained_value / size_value
            if retained_value < 0 or retained_value > size_value:
                violations.append(
                    {
                        "cohort": cohort_value,
                        "period": period_value,
                        "issue": "retained count outside [0, cohort size]",
                    }
                )
            if not isclose(rate_value, expected_rate, abs_tol=tolerance, rel_tol=0.0):
                violations.append(
                    {
                        "cohort": cohort_value,
                        "period": period_value,
                        "issue": "rate does not match retained / size",
                        "reported": rate_value,
                        "computed": round(expected_rate, 8),
                    }
                )
            if period_value == 0:
                has_period_zero = True
                if not isclose(rate_value, 1.0, abs_tol=tolerance, rel_tol=0.0):
                    violations.append(
                        {
                            "cohort": cohort_value,
                            "period": 0,
                            "issue": "period-zero retention is not 100%",
                            "reported": rate_value,
                        }
                    )
            if (
                monotonic
                and previous_retained is not None
                and retained_value > previous_retained
            ):
                violations.append(
                    {
                        "cohort": cohort_value,
                        "period": period_value,
                        "issue": "retained count increases in a strict retention cohort",
                        "previous": previous_retained,
                        "current": retained_value,
                    }
                )
            previous_retained = retained_value
        if not has_period_zero:
            violations.append(
                {"cohort": cohort_value, "issue": "period zero is missing"}
            )

    return _result(
        not violations,
        check_id=check_id,
        check_type="cohort_integrity",
        severity=severity,
        pass_message=f"All {len(groups)} cohort(s) preserve their analytical contract.",
        fail_message=f"{len(violations)} cohort integrity issue(s) found.",
        observed={"cohorts": len(groups), "violations": len(violations)},
        expected={
            "stable_denominator": True,
            "period_zero_rate": 1.0,
            "retained_not_above_size": True,
            "monotonic": monotonic,
            "tolerance": tolerance,
        },
        evidence=violations,
        why_it_matters=(
            "Changing denominators or malformed cohort shapes can turn retention into a misleading KPI."
        ),
        suggested_fix=(
            "Freeze cohort membership at entry, retain zero-activity rows, and recompute each rate."
        ),
    )
