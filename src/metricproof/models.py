"""Result models shared by the audit engine and renderers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    """One evidence-rich analytical assertion."""

    check_id: str
    check_type: str
    status: str
    severity: str
    message: str
    observed: Any = None
    expected: Any = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    why_it_matters: str = ""
    suggested_fix: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditReport:
    """Collection of check results for one contract execution."""

    title: str
    results: list[CheckResult]
    datasets: dict[str, int]
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def counts(self) -> dict[str, int]:
        counts = {"pass": 0, "fail": 0, "error": 0}
        for result in self.results:
            counts[result.status] = counts.get(result.status, 0) + 1
        return counts

    @property
    def passed(self) -> bool:
        return all(
            result.status == "pass"
            or (result.status == "fail" and result.severity in {"warning", "info"})
            for result in self.results
        )

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "generated_at": self.generated_at,
            "passed": self.passed,
            "counts": self.counts,
            "datasets": self.datasets,
            "results": [result.to_dict() for result in self.results],
        }
