"""Tracking backend infrastructure.

This module provides a pluggable tracking backend system.
"""

from .backend import TrackingBackend
from .constants import OperationStatus
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
from .factory import create_tracking_backend
from .noop import NoOpFallbackBackend

__all__ = [
    # Core protocol
    "TrackingBackend",
    # Factory
    "create_tracking_backend",
    # Events
    "ExperimentStartEvent",
    "ExperimentCompletedEvent",
    "ModelRunStartEvent",
    "ModelRunCompletedEvent",
    "InferenceStartEvent",
    "InferenceCompletedEvent",
    "ResultsAnalyzedEvent",
    "ArtifactGeneratedEvent",
    # Constants
    "OperationStatus",
    # Backends
    "NoOpFallbackBackend",
]
