"""Vendored evee core engine for POC."""
from __future__ import annotations

from .config import Config, ConnectionConfig, DatasetConfig, MetricConfig, TargetVariantConfig, ModelVariantConfig
from .decorators import (
    DATASET_REGISTRY,
    METRIC_REGISTRY,
    TARGET_REGISTRY,
    MODEL_REGISTRY,
    BaseDataset,
    BaseMetric,
    BaseTarget,
    BaseModel,
    dataset,
    metric,
    target,
    model,
)
from .discovery import discover_components
from .evaluator import ModelEvaluator
from .models import EvaluationOutput, ExecutionContext, InferenceOutput

# Import built-in datasets to register them
from . import datasets as _datasets  # noqa: F401

# Import SDK metric bridges to register real evaluators as @metric
from . import datasets as _datasets  # noqa: F401

__all__ = [
    "Config",
    "ConnectionConfig",
    "DatasetConfig",
    "MetricConfig",
    "TargetVariantConfig",
    "ModelVariantConfig",
    "BaseDataset",
    "BaseMetric",
    "BaseTarget",
    "BaseModel",
    "dataset",
    "metric",
    "target",
    "model",
    "DATASET_REGISTRY",
    "METRIC_REGISTRY",
    "TARGET_REGISTRY",
    "MODEL_REGISTRY",
    "discover_components",
    "ModelEvaluator",
    "EvaluationOutput",
    "ExecutionContext",
    "InferenceOutput",
]
