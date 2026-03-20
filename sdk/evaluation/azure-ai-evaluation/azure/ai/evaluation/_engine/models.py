"""Data models for engine."""
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
    tracking_enabled: bool = True
    model_variant_id: str = ""


@dataclass
class InferenceOutput:
    """Output of a model inference process."""

    output: Any
    model_name: str
    record: Dict[str, Any]
    args: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "output": self.output,
            "model_name": self.model_name,
            "record": self.record,
            "args": self.args,
        }


@dataclass
class EvaluationOutput:
    """Output of a model evaluation process."""

    run_id: str
    inference_output: InferenceOutput
    metrics: Dict[str, Dict[str, Any]]
    system_metrics: Dict[str, Dict[str, Any]]
    model_display_name: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            **self.inference_output.to_dict(),
            "run_id": self.run_id,
            "metrics": self.metrics,
            "system_metrics": self.system_metrics,
            "model_display_name": self.model_display_name,
            "metadata": self.metadata,
        }
