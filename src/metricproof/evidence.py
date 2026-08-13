"""Stable evidence primitives shared by MetricProof and domain integrations."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._version import __version__
from .models import CheckResult

REPORT_SCHEMA_VERSION = "1.0"


def hash_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return a SHA-256 digest without loading the entire artifact into memory."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ProducerInfo:
    """Software identity recorded in an evidence report."""

    name: str = "metricproof"
    version: str = __version__

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactEvidence:
    """Identity and provenance for one audited input artifact."""

    name: str
    uri: str
    sha256: str
    size_bytes: int
    media_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceReport:
    """Versioned, domain-neutral evidence report."""

    report_type: str
    title: str
    results: list[CheckResult]
    artifacts: list[ArtifactEvidence] = field(default_factory=list)
    producer: ProducerInfo = field(default_factory=ProducerInfo)
    context: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: str = REPORT_SCHEMA_VERSION

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
        """Return the canonical report payload described by evidence-v1.schema.json."""

        return {
            "schema_version": self.schema_version,
            "report_type": self.report_type,
            "title": self.title,
            "generated_at": self.generated_at,
            "producer": self.producer.to_dict(),
            "passed": self.passed,
            "counts": self.counts,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "results": [result.to_dict() for result in self.results],
            "context": self.context,
        }
