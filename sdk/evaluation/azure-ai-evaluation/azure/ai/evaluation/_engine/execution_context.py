"""ExecutionContext data model."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ExecutionContext:
    """Context provided to experiment components during execution."""

    connections_registry: Dict[str, Any] = field(default_factory=dict)
    experiment_name: str = ""
    experiment_version: str = ""
    experiment_dir: Optional[Path] = None
    output_path: str = ""
    model_variant_id: str = ""
