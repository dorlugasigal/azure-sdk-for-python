"""No-op tracking backend (default when tracking disabled)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .backend import TrackingBackend
from .events import (
    ArtifactGeneratedEvent,
    ExperimentCompletedEvent,
    ExperimentStartEvent,
    InferenceCompletedEvent,
    InferenceStartEvent,
    ModelRunCompletedEvent,
    ModelRunStartEvent,
    ResultsAnalyzedEvent,
)


class NoOpFallbackBackend(TrackingBackend):
    """No-op tracking backend — all methods are silent no-ops."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)

    def start_run(self, event: ModelRunStartEvent) -> Optional[str]:
        """Start a run and return the run name as run ID."""
        return event.run_id

    def on_experiment_started(self, event: ExperimentStartEvent) -> None:
        pass

    def on_experiment_completed(self, event: ExperimentCompletedEvent) -> None:
        pass

    def on_run_completed(self, event: ModelRunCompletedEvent) -> None:
        pass

    def on_inference_started(self, event: InferenceStartEvent) -> None:
        pass

    def on_inference_completed(self, event: InferenceCompletedEvent) -> None:
        pass

    def on_results_analyzed(self, event: ResultsAnalyzedEvent) -> None:
        pass

    def on_artifact_generated(self, event: ArtifactGeneratedEvent) -> None:
        pass
