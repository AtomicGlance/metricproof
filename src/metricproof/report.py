"""Human- and machine-readable report renderers."""

from __future__ import annotations

import json
from typing import Any

from .models import AuditReport


def render_text(report: AuditReport) -> str:
    badge = "PASS" if report.passed else "FAIL"
    counts = report.counts
    lines = [
        f"MetricProof: {report.title}",
        f"Result: {badge} | {counts['pass']} passed, {counts['fail']} failed, {counts['error']} errors",
        "",
    ]
    for result in report.results:
        lines.append(
            f"[{result.status.upper():5}] {result.check_id} ({result.check_type})"
        )
        lines.append(f"        {result.message}")
        if not result.passed and result.suggested_fix:
            lines.append(f"        Fix: {result.suggested_fix}")
    return "\n".join(lines)


def _cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: AuditReport) -> str:
    result_label = "PASS" if report.passed else "FAIL"
    counts = report.counts
    lines = [
        f"# {report.title}",
        "",
        f"**Audit result: {result_label}** — {counts['pass']} passed, "
        f"{counts['fail']} failed, {counts['error']} errors.",
        "",
        "## Dataset inventory",
        "",
        "| Dataset | Rows |",
        "|---|---:|",
    ]
    lines.extend(f"| {_cell(name)} | {count} |" for name, count in report.datasets.items())
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| Status | Check | Type | Finding |",
            "|---|---|---|---|",
        ]
    )
    for result in report.results:
        lines.append(
            f"| {result.status.upper()} | {_cell(result.check_id)} | "
            f"{_cell(result.check_type)} | {_cell(result.message)} |"
        )

    failures = [result for result in report.results if not result.passed]
    if failures:
        lines.extend(["", "## Actionable failures", ""])
        for result in failures:
            lines.extend(
                [
                    f"### {result.check_id}",
                    "",
                    f"- **Why it matters:** {result.why_it_matters}",
                    f"- **Suggested fix:** {result.suggested_fix}",
                    f"- **Observed:** `{_cell(result.observed)}`",
                    f"- **Expected:** `{_cell(result.expected)}`",
                ]
            )
            if result.evidence:
                lines.append(f"- **Evidence sample:** `{_cell(result.evidence)}`")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: AuditReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"
