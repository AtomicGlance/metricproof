"""JSON contract loader and audit dispatcher."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .checks import (
    check_cohort_integrity,
    check_numeric_range,
    check_population_preserved,
    check_ratio_consistency,
    check_reconciliation,
    check_unique_grain,
)
from .evidence import hash_file
from .models import AuditReport, CheckResult
from .plugins import Datasets, get_check_runner, register_check_type

SUPPORTED_CONTRACT_VERSIONS = frozenset({"1.0"})
SUPPORTED_SEVERITIES = frozenset({"critical", "warning", "info"})


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


def load_contract(contract_path: str | Path) -> tuple[Path, dict[str, Any]]:
    """Load and validate a versioned contract without reading its datasets."""

    path = Path(contract_path).expanduser().resolve()
    with path.open(encoding="utf-8") as handle:
        contract = json.load(handle)
    validate_contract_definition(contract)
    return path, contract


def validate_contract_definition(contract: Any) -> None:
    """Validate the stable fields common to built-in and plugin contracts."""

    if not isinstance(contract, dict):
        raise ValueError("contract root must be a JSON object")
    unknown_keys = sorted(
        set(contract) - {"contract_version", "title", "datasets", "checks"}
    )
    if unknown_keys:
        raise ValueError(f"unknown contract fields: {', '.join(unknown_keys)}")

    version = contract.get("contract_version")
    if not isinstance(version, str) or not version:
        raise ValueError("contract requires string 'contract_version'")
    if version not in SUPPORTED_CONTRACT_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_CONTRACT_VERSIONS))
        raise ValueError(
            f"unsupported contract_version {version!r}; supported versions: {supported}"
        )

    dataset_specs = contract.get("datasets")
    checks = contract.get("checks")
    if not isinstance(dataset_specs, dict) or not dataset_specs:
        raise ValueError("contract requires non-empty object 'datasets'")
    if not isinstance(checks, list):
        raise ValueError("contract requires array 'checks'")

    for name, spec in dataset_specs.items():
        if not isinstance(name, str) or not name:
            raise ValueError("dataset names must be non-empty strings")
        relative_path = spec.get("path") if isinstance(spec, dict) else spec
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError(
                f"dataset {name!r} must be a path string or an object with a 'path' string"
            )

    seen_ids: set[str] = set()
    for index, check in enumerate(checks, start=1):
        if not isinstance(check, Mapping):
            raise ValueError(f"check {index} must be an object")
        check_id = check.get("id")
        if not isinstance(check_id, str) or not check_id:
            raise ValueError(f"check {index} requires a non-empty string 'id'")
        if check_id in seen_ids:
            raise ValueError(f"duplicate check id: {check_id!r}")
        seen_ids.add(check_id)
        check_type = check.get("type")
        if not isinstance(check_type, str) or not check_type:
            raise ValueError(f"check {check_id!r} requires a non-empty string 'type'")
        severity = check.get("severity", "critical")
        if severity not in SUPPORTED_SEVERITIES:
            allowed = ", ".join(sorted(SUPPORTED_SEVERITIES))
            raise ValueError(
                f"check {check_id!r} has invalid severity {severity!r}; use {allowed}"
            )


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

    path, contract = load_contract(contract_path)
    dataset_specs = contract["datasets"]
    checks = contract["checks"]

    datasets: dict[str, list[dict[str, Any]]] = {}
    dataset_metadata: dict[str, dict[str, Any]] = {}
    for name, spec in dataset_specs.items():
        relative_path = spec["path"] if isinstance(spec, dict) else spec
        dataset_path = (path.parent / relative_path).resolve()
        rows = _load_rows(dataset_path)
        datasets[name] = rows
        dataset_metadata[name] = {
            "source": str(relative_path),
            "rows": len(rows),
            "size_bytes": dataset_path.stat().st_size,
            "sha256": hash_file(dataset_path),
        }

    results: list[CheckResult] = []
    for index, raw_check in enumerate(checks, start=1):
        check = dict(raw_check)
        check.setdefault("id", f"check-{index}")
        check_type = check.get("type")
        severity = str(check.get("severity", "critical"))
        try:
            result = get_check_runner(check_type)(check, datasets, severity)
        except (KeyError, TypeError, ValueError) as exc:
            result = _error_result(check, exc)
        results.append(result)

    return AuditReport(
        title=str(contract.get("title", path.stem)),
        results=results,
        datasets={name: len(rows) for name, rows in datasets.items()},
        dataset_metadata=dataset_metadata,
        contract_version=str(contract["contract_version"]),
        contract_metadata={
            "source": path.name,
            "sha256": hash_file(path),
        },
    )


def _unique_grain(
    check: Mapping[str, Any], datasets: Datasets, severity: str
) -> CheckResult:
    common = {"check_id": str(check["id"]), "severity": severity}
    return check_unique_grain(datasets[check["dataset"]], check["columns"], **common)


def _numeric_range(
    check: Mapping[str, Any], datasets: Datasets, severity: str
) -> CheckResult:
    return check_numeric_range(
        datasets[check["dataset"]],
        check["column"],
        minimum=check.get("minimum"),
        maximum=check.get("maximum"),
        check_id=str(check["id"]),
        severity=severity,
    )


def _ratio_consistency(
    check: Mapping[str, Any], datasets: Datasets, severity: str
) -> CheckResult:
    return check_ratio_consistency(
        datasets[check["dataset"]],
        check["numerator"],
        check["denominator"],
        check["rate"],
        tolerance=float(check.get("tolerance", 0.0001)),
        check_id=str(check["id"]),
        severity=severity,
    )


def _reconciliation(
    check: Mapping[str, Any], datasets: Datasets, severity: str
) -> CheckResult:
    left = check["left"]
    right = check["right"]
    return check_reconciliation(
        datasets[left["dataset"]],
        datasets[right["dataset"]],
        left_column=left["column"],
        right_column=right["column"],
        aggregate=str(check.get("aggregate", "sum")),
        tolerance=float(check.get("tolerance", 0.0)),
        check_id=str(check["id"]),
        severity=severity,
    )


def _population_preserved(
    check: Mapping[str, Any], datasets: Datasets, severity: str
) -> CheckResult:
    return check_population_preserved(
        datasets[check["baseline"]],
        datasets[check["evaluated"]],
        check["key"],
        minimum_coverage=float(check.get("minimum_coverage", 1.0)),
        allow_unexpected=bool(check.get("allow_unexpected", False)),
        check_id=str(check["id"]),
        severity=severity,
    )


def _cohort_integrity(
    check: Mapping[str, Any], datasets: Datasets, severity: str
) -> CheckResult:
    return check_cohort_integrity(
        datasets[check["dataset"]],
        cohort=check["cohort"],
        period=check["period"],
        retained=check["retained"],
        size=check["size"],
        rate=check["rate"],
        monotonic=bool(check.get("monotonic", True)),
        tolerance=float(check.get("tolerance", 0.0001)),
        check_id=str(check["id"]),
        severity=severity,
    )


for _name, _runner in {
    "unique_grain": _unique_grain,
    "numeric_range": _numeric_range,
    "ratio_consistency": _ratio_consistency,
    "reconciliation": _reconciliation,
    "population_preserved": _population_preserved,
    "cohort_integrity": _cohort_integrity,
}.items():
    register_check_type(_name, _runner)
