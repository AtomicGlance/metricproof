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
from .models import AuditReport, CheckResult

__all__ = [
    "AuditReport",
    "CheckResult",
    "audit_contract",
    "check_cohort_integrity",
    "check_numeric_range",
    "check_population_preserved",
    "check_ratio_consistency",
    "check_reconciliation",
    "check_unique_grain",
]

__version__ = "0.1.0"
