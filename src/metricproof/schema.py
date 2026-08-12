"""Access to the versioned JSON schemas shipped with MetricProof."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

SCHEMA_FILES = {
    "contract": "contract-v1.schema.json",
    "evidence": "evidence-v1.schema.json",
}


def load_schema(kind: str) -> dict[str, Any]:
    """Load a bundled schema by its CLI-facing name."""

    try:
        filename = SCHEMA_FILES[kind]
    except KeyError as exc:
        raise ValueError(f"unknown schema {kind!r}") from exc
    resource = files("metricproof.schemas").joinpath(filename)
    return json.loads(resource.read_text(encoding="utf-8"))
