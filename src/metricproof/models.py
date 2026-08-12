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
    dataset_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    contract_version: str = "1.0"
    contract_metadata: dict[str, Any] = field(default_factory=dict)

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

    def to_evidence_report(self):
        """Convert the analytical result into the stable shared evidence model."""

        from .evidence import ArtifactEvidence, EvidenceReport

        artifacts = []
        for name, rows in self.datasets.items():
            metadata = dict(self.dataset_metadata.get(name, {}))
            source = str(metadata.pop("source", name))
            size_bytes = int(metadata.pop("size_bytes", 0))
            sha256 = str(metadata.pop("sha256", ""))
            artifacts.append(
                ArtifactEvidence(
                    name=name,
                    uri=source,
                    sha256=sha256,
                    size_bytes=size_bytes,
                    media_type=_media_type(source),
                    metadata={"rows": rows, **metadata},
                )
            )
        return EvidenceReport(
            report_type="metric-audit",
            title=self.title,
            results=self.results,
            artifacts=artifacts,
            context={
                "contract_version": self.contract_version,
                "contract": self.contract_metadata,
            },
            generated_at=self.generated_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.to_evidence_report().to_dict()


def _media_type(source: str) -> str | None:
    suffix = source.lower().rsplit(".", maxsplit=1)[-1]
    return {
        "csv": "text/csv",
        "json": "application/json",
        "parquet": "application/vnd.apache.parquet",
    }.get(suffix)
