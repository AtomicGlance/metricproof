"""Registry and entry-point discovery for analytical check plugins."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib.metadata import entry_points
from typing import Any, Protocol

from .models import CheckResult

DatasetRows = Sequence[Mapping[str, Any]]
Datasets = Mapping[str, DatasetRows]


class CheckRunner(Protocol):
    """Callable contract implemented by built-in and third-party checks."""

    def __call__(
        self,
        check: Mapping[str, Any],
        datasets: Datasets,
        severity: str,
    ) -> CheckResult: ...


_CHECKS: dict[str, CheckRunner] = {}
_ENTRY_POINTS_LOADED = False


def register_check_type(
    name: str,
    runner: CheckRunner,
    *,
    replace: bool = False,
) -> None:
    """Register a check runner under a stable contract type name."""

    if not isinstance(name, str) or not name.strip():
        raise ValueError("check type name must be a non-empty string")
    if not callable(runner):
        raise TypeError("check runner must be callable")
    normalized = name.strip()
    if normalized in _CHECKS and not replace:
        raise ValueError(f"check type {normalized!r} is already registered")
    _CHECKS[normalized] = runner


def unregister_check_type(name: str) -> None:
    """Remove a check type. Primarily useful for isolated plugin tests."""

    _CHECKS.pop(name, None)


def _load_entry_point_checks() -> None:
    global _ENTRY_POINTS_LOADED
    if _ENTRY_POINTS_LOADED:
        return
    _ENTRY_POINTS_LOADED = True
    for entry_point in entry_points(group="metricproof.checks"):
        register_check_type(entry_point.name, entry_point.load())


def get_check_runner(name: str) -> CheckRunner:
    """Return a registered runner, discovering installed plugins once if needed."""

    _load_entry_point_checks()
    try:
        return _CHECKS[name]
    except KeyError as exc:
        available = ", ".join(sorted(_CHECKS)) or "none"
        raise ValueError(
            f"unsupported check type: {name!r}; available check types: {available}"
        ) from exc


def available_check_types() -> tuple[str, ...]:
    """Return all built-in and discovered plugin check type names."""

    _load_entry_point_checks()
    return tuple(sorted(_CHECKS))
