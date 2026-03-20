"""TrackingBackend base class with lifecycle hooks.

Only start_run() is required; all other methods are optional no-ops.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

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


class TrackingBackend:
    """Base class for tracking backends.

    Methods ordered chronologically by typical execution order.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}

    def on_startup(self) -> None:
        """Handle backend startup (optional)."""
        pass

    def on_experiment_started(self, event: ExperimentStartEvent) -> None:
        """Handle experiment start event."""
        pass

    def on_experiment_completed(self, event: ExperimentCompletedEvent) -> None:
        """Handle experiment completion event."""
        pass

    def start_run(self, event: ModelRunStartEvent) -> Optional[str]:
        """Start a new model evaluation run. Returns backend-specific run ID."""
        raise NotImplementedError("Subclasses must implement start_run()")

    def on_inference_started(self, event: InferenceStartEvent) -> None:
        """Handle inference start (optional)."""
        pass

    def on_inference_completed(self, event: InferenceCompletedEvent) -> None:
        """Handle inference completion (optional)."""
        pass

    def on_results_analyzed(self, event: ResultsAnalyzedEvent) -> None:
        """Handle results analysis (optional)."""
        pass

    def on_artifact_generated(self, event: ArtifactGeneratedEvent) -> None:
        """Handle artifact generation (optional)."""
        pass

    def on_run_completed(self, event: ModelRunCompletedEvent) -> None:
        """Handle model run completion (optional)."""
        pass

    def on_shutdown(self) -> None:
        """Handle backend shutdown (optional)."""
        pass
