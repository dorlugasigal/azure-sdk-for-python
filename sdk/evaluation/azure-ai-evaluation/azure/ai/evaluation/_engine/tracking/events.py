"""Event dataclasses for tracking lifecycle methods."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import OperationStatus


@dataclass(frozen=True)
class ModelRunStartEvent:
    """Event for starting a model evaluation run."""

    run_id: str
    """System-generated run identifier."""

    model_name: str
    """Name of the model being evaluated."""


@dataclass(frozen=True)
class ExperimentStartEvent:
    """Event for experiment start."""

    experiment_name: str
    """Name of the experiment."""

    config: Dict[str, Any]
    """Full configuration dictionary."""


@dataclass(frozen=True)
class ExperimentCompletedEvent:
    """Event for experiment completion."""

    experiment_name: str
    """Name of the experiment."""


@dataclass(frozen=True)
class ResultsAnalyzedEvent:
    """Event for results analysis completion."""

    run_id: str
    """System-generated run identifier."""

    metrics: Dict[str, Any]
    """Computed metrics."""

    tags: Optional[Dict[str, str]] = None
    """Optional metadata tags."""


@dataclass(frozen=True)
class ArtifactGeneratedEvent:
    """Event for artifact generation."""

    run_id: str
    """System-generated run identifier."""

    artifact_path: Path
    """Path to generated artifact."""

    artifact_type: str
    """Type of artifact (e.g., 'html', 'json', 'jsonl', 'csv', 'text')."""


@dataclass(frozen=True)
class ModelRunCompletedEvent:
    """Event for model evaluation run completion."""

    run_id: str
    """System-generated run identifier."""

    status: OperationStatus
    """Run status (use OperationStatus.SUCCESS or OperationStatus.FAILED)."""

    error: Optional[str] = None
    """Error message if status is OperationStatus.FAILED."""


@dataclass(frozen=True)
class InferenceStartEvent:
    """Event for inference start (per-record tracing)."""

    run_id: str
    """System-generated run identifier."""

    record_id: str
    """Unique identifier for this dataset record."""

    input_data: Dict[str, Any]
    """Input data for this inference (includes prompt and any context)."""


@dataclass(frozen=True)
class InferenceCompletedEvent:
    """Event for inference completion (per-record tracing)."""

    run_id: str
    """System-generated run identifier."""

    record_id: str
    """Unique identifier for this dataset record."""

    output_data: Dict[str, Any]
    """Output data from this inference (includes response and metadata)."""

    duration_ms: float
    """Inference duration in milliseconds."""

    status: OperationStatus
    """Inference status (use OperationStatus.SUCCESS or OperationStatus.FAILED)."""
