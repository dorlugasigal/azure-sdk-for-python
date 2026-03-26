"""Evee core engine — lazy-loaded to avoid slow startup.

All heavy imports are deferred until the symbol is actually accessed.
This keeps ``import azure.ai.evaluation._engine`` fast for CLI startup.
"""
from __future__ import annotations

__all__ = [
    "Config",
    "ConnectionConfig",
    "DatasetConfig",
    "EvaluatorConfig",
    "TargetVariantConfig",
    "DatasetFactory",
    "BUILTIN_DATASET_TYPES",
    "BaseDataset",
    "BaseEvaluator",
    "BaseTarget",
    "dataset",
    "evaluator",
    "target",
    "DATASET_REGISTRY",
    "EVALUATOR_REGISTRY",
    "TARGET_REGISTRY",
    "discover_components",
    "EnvironmentResolver",
    "ModelEvaluator",
    "EvaluationOutput",
    "ExecutionContext",
    "InferenceOutput",
    "AggregatedMetrics",
    "MetricsAggregator",
    "ProgressTracker",
    "run_preflight_checks",
    "get_console",
    "setup_logger",
    "LocalMetricsLogger",
]

# Lazy import mapping: attribute name → (module, name)
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "Config": (".config", "Config"),
    "ConnectionConfig": (".config", "ConnectionConfig"),
    "DatasetConfig": (".config", "DatasetConfig"),
    "EvaluatorConfig": (".config", "EvaluatorConfig"),
    "TargetVariantConfig": (".config", "TargetVariantConfig"),
    "DatasetFactory": (".dataset_factory", "DatasetFactory"),
    "BUILTIN_DATASET_TYPES": (".dataset_factory", "BUILTIN_DATASET_TYPES"),
    "BaseDataset": (".decorators", "BaseDataset"),
    "BaseEvaluator": (".decorators", "BaseEvaluator"),
    "BaseTarget": (".decorators", "BaseTarget"),
    "dataset": (".decorators", "dataset"),
    "evaluator": (".decorators", "evaluator"),
    "target": (".decorators", "target"),
    "DATASET_REGISTRY": (".decorators", "DATASET_REGISTRY"),
    "EVALUATOR_REGISTRY": (".decorators", "EVALUATOR_REGISTRY"),
    "TARGET_REGISTRY": (".decorators", "TARGET_REGISTRY"),
    "discover_components": (".discovery", "discover_components"),
    "EnvironmentResolver": (".environment", "EnvironmentResolver"),
    "ModelEvaluator": (".evaluator", "ModelEvaluator"),
    "EvaluationOutput": (".models", "EvaluationOutput"),
    "ExecutionContext": (".models", "ExecutionContext"),
    "InferenceOutput": (".models", "InferenceOutput"),
    "AggregatedMetrics": (".metrics_aggregator", "AggregatedMetrics"),
    "MetricsAggregator": (".metrics_aggregator", "MetricsAggregator"),
    "ProgressTracker": (".progress_tracker", "ProgressTracker"),
    "run_preflight_checks": (".preflight", "run_preflight_checks"),
    "get_console": (".logging", "get_console"),
    "setup_logger": (".logging", "setup_logger"),
    "LocalMetricsLogger": (".logging", "LocalMetricsLogger"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path, __name__)
        value = getattr(module, attr_name)
        # Cache it on the module so __getattr__ isn't called again
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
