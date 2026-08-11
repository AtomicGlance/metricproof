"""JSON contract loader and audit dispatcher."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .checks import (
    check_cohort_integrity,
    check_numeric_range,
    check_population_preserved,
    check_ratio_consistency,
    check_reconciliation,
    check_unique_grain,
)
from .models import AuditReport, CheckResult


def _load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if suffix == ".json":
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list) or not all(
            isinstance(row, dict) for row in payload
        ):
            raise ValueError(f"{path} must contain a JSON array of objects")
        return payload
    raise ValueError(f"unsupported dataset format for {path}; use CSV or JSON")


def _sha256(path: Path) -> str:
    """Return the SHA-256 fingerprint of the exact dataset file read."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _error_result(check: dict[str, Any], exc: Exception) -> CheckResult:
    return CheckResult(
        check_id=str(check.get("id", "unnamed-check")),
        check_type=str(check.get("type", "unknown")),
        status="error",
        severity="critical",
        message=f"Check could not run: {exc}",
        observed={"exception": type(exc).__name__},
        expected="A valid check definition and compatible dataset columns.",
        why_it_matters="An unexecuted assertion leaves the metric unverified.",
        suggested_fix="Correct the contract or source data, then rerun the audit.",
    )


def audit_contract(contract_path: str | Path) -> AuditReport:
    """Run every assertion in a JSON contract and return an audit report."""

    path = Path(contract_path).resolve()
    with path.open(encoding="utf-8") as handle:
        contract = json.load(handle)
    if not isinstance(contract, dict):
        raise ValueError("contract root must be a JSON object")

    dataset_specs = contract.get("datasets")
    checks = contract.get("checks")
    if not isinstance(dataset_specs, dict) or not isinstance(checks, list):
        raise ValueError("contract requires object 'datasets' and array 'checks'")

    datasets: dict[str, list[dict[str, Any]]] = {}
    dataset_metadata: dict[str, dict[str, Any]] = {}
    for name, spec in dataset_specs.items():
        relative_path = spec["path"] if isinstance(spec, dict) else spec
        if not isinstance(relative_path, (str, Path)) or not str(relative_path):
            raise ValueError(
                f"dataset {name!r} must be a path string or an object with a 'path' string"
            )
        dataset_path = (path.parent / relative_path).resolve()
        rows = _load_rows(dataset_path)
        datasets[name] = rows
        dataset_metadata[name] = {
            "source": str(relative_path),
            "rows": len(rows),
            "size_bytes": dataset_path.stat().st_size,
            "sha256": _sha256(dataset_path),
        }

    results: list[CheckResult] = []
    for index, raw_check in enumerate(checks, start=1):
        check = dict(raw_check)
        check.setdefault("id", f"check-{index}")
        check_type = check.get("type")
        severity = str(check.get("severity", "critical"))
        try:
            result = _dispatch(check_type, check, datasets, severity)
        except (KeyError, TypeError, ValueError) as exc:
            result = _error_result(check, exc)
        results.append(result)

    return AuditReport(
        title=str(contract.get("title", path.stem)),
        results=results,
        datasets={name: len(rows) for name, rows in datasets.items()},
        dataset_metadata=dataset_metadata,
    )


def _dispatch(
    check_type: str,
    check: dict[str, Any],
    datasets: dict[str, list[dict[str, Any]]],
    severity: str,
) -> CheckResult:
    common = {"check_id": str(check["id"]), "severity": severity}
    if check_type == "unique_grain":
        return check_unique_grain(
            datasets[check["dataset"]], check["columns"], **common
        )
    if check_type == "numeric_range":
        return check_numeric_range(
            datasets[check["dataset"]],
            check["column"],
            minimum=check.get("minimum"),
            maximum=check.get("maximum"),
            **common,
        )
    if check_type == "ratio_consistency":
        return check_ratio_consistency(
            datasets[check["dataset"]],
            check["numerator"],
            check["denominator"],
            check["rate"],
            tolerance=float(check.get("tolerance", 0.0001)),
            **common,
        )
    if check_type == "reconciliation":
        left = check["left"]
        right = check["right"]
        return check_reconciliation(
            datasets[left["dataset"]],
            datasets[right["dataset"]],
            left_column=left["column"],
            right_column=right["column"],
            aggregate=str(check.get("aggregate", "sum")),
            tolerance=float(check.get("tolerance", 0.0)),
            **common,
        )
    if check_type == "population_preserved":
        return check_population_preserved(
            datasets[check["baseline"]],
            datasets[check["evaluated"]],
            check["key"],
            minimum_coverage=float(check.get("minimum_coverage", 1.0)),
            allow_unexpected=bool(check.get("allow_unexpected", False)),
            **common,
        )
    if check_type == "cohort_integrity":
        return check_cohort_integrity(
            datasets[check["dataset"]],
            cohort=check["cohort"],
            period=check["period"],
            retained=check["retained"],
            size=check["size"],
            rate=check["rate"],
            monotonic=bool(check.get("monotonic", True)),
            tolerance=float(check.get("tolerance", 0.0001)),
            **common,
        )
    raise ValueError(f"unsupported check type: {check_type!r}")
