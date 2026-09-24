"""MetricProof: executable checks for trustworthy analytical metrics."""

from ._version import __version__
from .checks import (
    check_cohort_integrity,
    check_numeric_range,
    check_population_preserved,
    check_ratio_consistency,
    check_reconciliation,
    check_unique_grain,
)
from .comparison import ComparisonReport, compare_reports
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
from .relational import check_grouped_reconciliation, check_join_integrity

__all__ = [
    "check_grouped_reconciliation",
    "check_join_integrity",
    "ComparisonReport",
    "compare_reports",
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
