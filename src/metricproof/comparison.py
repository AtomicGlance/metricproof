"""Offline comparison of saved metric audits. No data or plugins are executed."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from .schema import load_schema


def definition_digest(definition: dict) -> str:
    """Hash sorted JSON object keys; array order remains semantically significant."""
    return hashlib.sha256(
        json.dumps(
            definition, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _validate(value: Any, schema: dict, root: dict, path: str = "report") -> None:
    """Validate the subset of JSON Schema used by bundled evidence v1."""
    if "$ref" in schema:
        schema = root["$defs"][schema["$ref"].split("/")[-1]]
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "integer": int,
        "null": type(None),
    }
    kinds = schema.get("type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    if kinds and not any(type(value) is types[k] for k in kinds):
        raise ValueError(f"{path}: invalid type")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path}: unsupported value {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unsupported value")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{path}: empty string")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise ValueError(f"{path}: invalid fingerprint")
    if type(value) is int and value < schema.get("minimum", value):
        raise ValueError(f"{path}: below minimum")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}: missing {key}")
        props = schema.get("properties", {})
        for key, item in value.items():
            spec = props.get(key, schema.get("additionalProperties", {}))
            if spec is False:
                raise ValueError(f"{path}: unexpected {key}")
            if isinstance(spec, dict):
                _validate(item, spec, root, f"{path}.{key}")
    if isinstance(value, list):
        for item in value:
            _validate(item, schema.get("items", {}), root, path)


def _index(items: list, key: str) -> dict:
    result = {}
    for item in items:
        if item[key] in result:
            raise ValueError(f"duplicate {key}: {item[key]}")
        result[item[key]] = item
    return result


def _blocking(check: dict) -> bool:
    return check["status"] == "error" or (
        check["status"] == "fail" and check["severity"] == "critical"
    )


def _report(report: Any) -> tuple[dict, dict, dict]:
    if hasattr(report, "to_dict"):
        report = report.to_dict()
    # Reject non-JSON and non-finite values even inside free-form evidence.
    json.dumps(report, allow_nan=False)
    schema = load_schema("evidence")
    _validate(report, schema, schema)
    if report["report_type"] != "metric-audit":
        raise ValueError("comparison supports metric-audit reports only")
    checks = _index(report["results"], "check_id")
    artifacts = _index(report["artifacts"], "name")
    counts = {
        s: sum(c["status"] == s for c in checks.values())
        for s in ("pass", "fail", "error")
    }
    if report["counts"] != counts or report["passed"] != (
        not any(_blocking(c) for c in checks.values())
    ):
        raise ValueError("report summary contradicts check results")
    contract = report["context"].get("contract", {})
    if not isinstance(contract, dict):
        raise ValueError("contract metadata must be an object")
    provenance = contract.get("checks", {})
    if not isinstance(provenance, dict) or set(provenance) - set(checks):
        raise ValueError("invalid check provenance")
    for name, item in provenance.items():
        if not isinstance(item, dict) or not isinstance(item.get("definition"), dict):
            raise ValueError("invalid check definition provenance")
        definition = item["definition"]
        if item.get("sha256") != definition_digest(definition):
            raise ValueError("check definition fingerprint mismatch")
        if (
            definition.get("id") != name
            or definition.get("type") != checks[name]["check_type"]
        ):
            raise ValueError("check definition identity mismatch")
        runner = item.get("runner")
        if not isinstance(runner, dict) or not isinstance(runner.get("name"), str):
            raise ValueError("invalid runner provenance")
        if runner.get("version") is not None and not isinstance(runner["version"], str):
            raise ValueError("invalid runner version")
    return report, checks, artifacts


@dataclass
class ComparisonReport:
    """Comparison policy is separate from the current audit's own outcome."""

    changes: list[dict]
    warnings: list[str]
    regressions: list[str]
    current_failures: list[str]
    needs_review: bool

    @property
    def exit_code(self) -> int:
        return int(bool(self.regressions) or self.needs_review)

    def to_dict(self) -> dict:
        return {
            "comparison_version": "1.0",
            **asdict(self),
            "current_audit_passed": not self.current_failures,
            "policy_passed": self.exit_code == 0,
        }


def compare_reports(previous_report: Any, current_report: Any) -> ComparisonReport:
    """Compare evidence-v1 metric audits, conservatively gating uncertain changes."""
    old, before, old_assets = _report(previous_report)
    new, after, new_assets = _report(current_report)
    changes, warnings, regressions = [], [], []
    review = False

    def change(scope, name, field, previous, current):
        if previous != current:
            changes.append(
                dict(
                    scope=scope,
                    name=name,
                    field=field,
                    previous=previous,
                    current=current,
                )
            )

    for name in sorted(before.keys() | after.keys()):
        a, b = before.get(name), after.get(name)
        if a is None or b is None:
            change("check", name, "added" if a is None else "removed", a, b)
            if b and _blocking(b):
                regressions.append(name)
            if a and a["severity"] == "critical":
                review = True
            continue
        for field in ("status", "check_type", "severity", "observed", "expected"):
            change("check", name, field, a.get(field), b.get(field))
        if _blocking(b) and (
            not _blocking(a) or (b["status"] == "error" and a["status"] != "error")
        ):
            regressions.append(name)
        if any(a[f] != b[f] for f in ("severity", "check_type")):
            review = True
        pa = old["context"].get("contract", {}).get("checks", {}).get(name)
        pb = new["context"].get("contract", {}).get("checks", {}).get(name)
        if pa is None or pb is None:
            warnings.append(
                f"{name}: comparability unknown (missing definition provenance)"
            )
            review = True
        else:
            for field in ("definition", "runner"):
                change("check", name, field, pa[field], pb[field])
                review |= pa[field] != pb[field]
            if any(p["runner"].get("version") is None for p in (pa, pb)):
                warnings.append(
                    f"{name}: comparability unknown (runner version unavailable)"
                )
                review = True
    for name in sorted(old_assets.keys() | new_assets.keys()):
        a, b = old_assets.get(name), new_assets.get(name)
        if a is None or b is None:
            change("artifact", name, "added" if a is None else "removed", a, b)
        else:
            for field in ("sha256", "uri", "size_bytes"):
                change("artifact", name, field, a[field], b[field])
    change("report", "producer", "identity", old["producer"], new["producer"])
    for field in ("contract_version",):
        change(
            "report",
            "contract",
            field,
            old["context"].get(field),
            new["context"].get(field),
        )
        review |= old["context"].get(field) != new["context"].get(field)
    change(
        "report",
        "contract",
        "sha256",
        old["context"].get("contract", {}).get("sha256"),
        new["context"].get("contract", {}).get("sha256"),
    )
    review |= old["producer"] != new["producer"]
    return ComparisonReport(
        changes,
        warnings,
        regressions,
        sorted(n for n, c in after.items() if _blocking(c)),
        review,
    )


def render_comparison(report: ComparisonReport, format: str = "text") -> str:
    if format == "json":
        return json.dumps(report.to_dict(), indent=2, allow_nan=False) + "\n"
    lines = [
        f"Comparison: {'BLOCKED' if report.exit_code else 'PASS'}",
        f"Current audit: {'FAIL' if report.current_failures else 'PASS'}",
    ]
    for item in report.changes:
        lines.append(
            f"{item['scope']} {item['name']} - {item['field']}: "
            f"{json.dumps(item['previous'], sort_keys=True)} -> "
            f"{json.dumps(item['current'], sort_keys=True)}"
        )
    lines.extend(report.warnings)
    if report.current_failures:
        lines.append("Current blocking checks: " + ", ".join(report.current_failures))
    if report.needs_review:
        lines.append(
            "Review required: definitions, coverage, or comparability changed/unknown."
        )
    if format == "markdown":
        # Escape arbitrary report strings rather than permitting HTML injection.
        import html

        return "<pre>" + html.escape("\n".join(lines)) + "</pre>\n"
    return "\n".join(lines) + "\n"
