"""MetricProof: executable checks for trustworthy analytical metrics."""

from .checks import (
    check_cohort_integrity,
    check_numeric_range,
    check_population_preserved,
    check_ratio_consistency,
    check_reconciliation,
    check_unique_grain,
)
from .contract import audit_contract
from .evidence import (
    REPORT_SCHEMA_VERSION,
    ArtifactEvidence,
    EvidenceReport,
    ProducerInfo,
    hash_file,
)
from .models import AuditReport, CheckResult
from .plugins import available_check_types, register_check_type
from ._version import __version__

__all__ = [
    "AuditReport",
    "CheckResult",
    "ArtifactEvidence",
    "EvidenceReport",
    "ProducerInfo",
    "REPORT_SCHEMA_VERSION",
    "__version__",
    "audit_contract",
    "available_check_types",
    "check_cohort_integrity",
    "check_numeric_range",
    "check_population_preserved",
    "check_ratio_consistency",
    "check_reconciliation",
    "check_unique_grain",
    "hash_file",
    "register_check_type",
]
