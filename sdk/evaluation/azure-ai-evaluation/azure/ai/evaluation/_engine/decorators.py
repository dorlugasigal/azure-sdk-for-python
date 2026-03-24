"""Decorators and base classes for metrics, targets, and datasets."""
from __future__ import annotations

import inspect
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from numbers import Number
from typing import Any, Dict, List, Optional, TypeVar, Union, cast

from .models import ExecutionContext, InferenceOutput

T = TypeVar("T")

# Global registries
EVALUATOR_REGISTRY: Dict[str, type] = {}
TARGET_REGISTRY: Dict[str, type] = {}
DATASET_REGISTRY: Dict[str, type] = {}

# Backward compat alias
MODEL_REGISTRY = TARGET_REGISTRY


# Helper functions
def _get_missing_params(signature: inspect.Signature, config: Dict[str, Any]) -> set:
    """Get required parameters missing from config."""
    ignore = ["connections_registry", "context"]
    required = [
        p
        for p, info in signature.parameters.items()
        if p not in ["self", "return", "args", "kwargs", *ignore]
        and info.default == inspect.Parameter.empty
        and info.kind != inspect.Parameter.VAR_KEYWORD
    ]
    return set(required) - set(config.keys())


def _get_params_from_config(signature: inspect.Signature, config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract parameters from config that exist in signature."""
    config_params = set(config.keys())
    method_params = set(signature.parameters.keys())
    params = config_params.intersection(method_params)
    return {param: config[param] for param in params}


# Base classes
class BaseEvaluator(ABC):
    """Base class for all evaluators."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, context: Optional[ExecutionContext] = None):
        config = config or {}
        self.name = config.get("name", getattr(self.__class__, "_metric_name", self.__class__.__name__))
        self.display_name = config.get("display_name") or self.name
        self.context = context
        self.mapping = config.get("mapping", {})

    @abstractmethod
    def compute(self, **kwargs: Any) -> Dict[str, Any]:
        """Calculate metric for a single record."""
        ...

    @abstractmethod
    def aggregate(self, scores: List[Dict[str, Any]]) -> Dict[str, Number]:
        """Aggregate scores across multiple records."""
        ...

    def _get_mapped_fields(self, inference_output: InferenceOutput) -> Dict[str, Any]:
        """Map fields from inference output to metric inputs."""
        data = inference_output.to_dict()
        sources = {"model": data.get("output", {}), "dataset": data.get("record", {})}

        mapped_fields = {}
        for param, mapping in self.mapping.items():
            source, field = mapping.split(".", 1)
            try:
                mapped_fields[param] = sources[source][field]
            except KeyError as e:
                raise KeyError(
                    f"Field '{field}' not found in '{source}'. "
                    f"Please verify mapping for metric '{self.display_name}'"
                ) from e
        return mapped_fields


class BaseTarget(ABC):
    """Base class for all targets."""

    def __init__(self, context: Optional[ExecutionContext] = None):
        self.context = context

    @abstractmethod
    def infer(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Perform inference on input."""
        ...


# Backward compat alias
BaseModel = BaseTarget


class BaseDataset(ABC):
    """Base class for all datasets."""

    def __init__(self, context: Optional[ExecutionContext] = None):
        self.context = context

    @abstractmethod
    def __iter__(self) -> Iterator[Dict[str, Any]]:
        """Yield records from the dataset."""
        ...

    @abstractmethod
    def __len__(self) -> int:
        """Return number of records."""
        ...


# Decorators
def evaluator(name: Optional[str] = None) -> Callable[[type[T]], type[T]]:
    """Decorator for creating evaluators."""

    def decorator(cls: type[T]) -> type[T]:
        evaluator_name = name if name is not None else cls.__name__

        if evaluator_name in EVALUATOR_REGISTRY:
            return cast(type[T], EVALUATOR_REGISTRY[evaluator_name])

        class EvaluatorWrapper(BaseEvaluator):
            def __init__(self, config: Optional[Dict[str, Any]] = None, context: Optional[ExecutionContext] = None, **extra_kwargs: Any):
                config = config or {}
                # Ensure name is set
                if "name" not in config:
                    config = {**config, "name": evaluator_name}
                if "mapping" not in config:
                    config = {**config, "mapping": {}}
                super().__init__(config, context)

                # Validate mapping format if provided
                if self.mapping:
                    pattern = re.compile(r"^(model|dataset)\.[^\.]+$")
                    for field, mapping_val in self.mapping.items():
                        if not pattern.match(mapping_val):
                            raise ValueError(
                                f"Invalid mapping '{mapping_val}' for field '{field}' in metric '{self.name}': "
                                f"expected format 'model.X' or 'dataset.X'"
                            )

                # Create inner metric instance — pass config values + extra kwargs
                cls_sig = inspect.signature(cls.__init__)
                init_params: Dict[str, Any] = {}
                for param_name_inner, param in cls_sig.parameters.items():
                    if param_name_inner == "self":
                        continue
                    if param_name_inner == "connections_registry":
                        init_params[param_name_inner] = self.context.connections_registry if self.context else {}
                    elif param_name_inner == "context":
                        init_params[param_name_inner] = self.context
                    elif param_name_inner in extra_kwargs:
                        init_params[param_name_inner] = extra_kwargs[param_name_inner]
                    elif param_name_inner in config:
                        init_params[param_name_inner] = config[param_name_inner]

                self.inner = cls(**init_params)

            def compute(self, inference_output: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
                """Delegate to inner metric. Supports both evee engine and direct kwargs."""
                if kwargs and not inference_output:
                    # Direct kwargs mode (programmatic API)
                    return self.inner.compute(**kwargs)
                elif inference_output:
                    # Evee engine mode (with field mapping)
                    fields = self._get_mapped_fields(inference_output)
                    # Pass inference_output so evaluators can access agent_trace
                    fields["inference_output"] = inference_output
                    return self.inner.compute(**fields)
                else:
                    return self.inner.compute()

            def aggregate(self, scores: List[Dict[str, Any]]) -> Dict[str, Number]:
                """Delegate to inner metric."""
                return self.inner.aggregate(scores)

        EvaluatorWrapper.__name__ = cls.__name__
        EvaluatorWrapper.__doc__ = cls.__doc__
        EvaluatorWrapper.__module__ = cls.__module__
        EvaluatorWrapper.__qualname__ = cls.__qualname__

        EVALUATOR_REGISTRY[evaluator_name] = EvaluatorWrapper
        return cast(type[T], EvaluatorWrapper)

    return decorator


def target(name: Optional[str] = None) -> Callable[[type[T]], type[T]]:
    """Decorator for creating targets."""

    def decorator(cls: type[T]) -> type[T]:
        target_name = name if name is not None else cls.__name__

        if target_name in TARGET_REGISTRY:
            raise ValueError(f"Target '{target_name}' already registered")

        class TargetWrapper(BaseTarget):
            def __init__(self, config: Dict[str, Any], context: Optional[ExecutionContext] = None):
                super().__init__(context)

                cls_sig = inspect.signature(cls.__init__)
                missing = _get_missing_params(cls_sig, config)
                if missing:
                    raise ValueError(f"Missing required parameters for target '{cls.__name__}': {', '.join(missing)}")

                init_params = _get_params_from_config(cls_sig, config)
                if "connections_registry" in cls_sig.parameters:
                    init_params["connections_registry"] = self.context.connections_registry if self.context else {}
                if "context" in cls_sig.parameters:
                    init_params["context"] = self.context

                self.inner = cls(**init_params)

            def infer(self, input: Dict[str, Any]) -> Dict[str, Any]:
                """Delegate to inner target."""
                return self.inner.infer(input)

        TargetWrapper.__name__ = cls.__name__
        TargetWrapper.__doc__ = cls.__doc__
        TargetWrapper.__module__ = cls.__module__
        TargetWrapper.__qualname__ = cls.__qualname__

        TARGET_REGISTRY[target_name] = TargetWrapper
        return cast(type[T], TargetWrapper)

    return decorator


# Backward compat alias
model = target


def dataset(name: Optional[str] = None) -> Callable[[type[T]], type["BaseDataset"]]:
    """Decorator for creating datasets."""

    def decorator(cls: type[T]) -> type["BaseDataset"]:
        dataset_name = name if name is not None else cls.__name__

        if dataset_name in DATASET_REGISTRY:
            raise ValueError(f"Dataset '{dataset_name}' already registered")

        class DatasetWrapper(BaseDataset):
            def __init__(self, config: Dict[str, Any], context: Optional[ExecutionContext] = None):
                super().__init__(context)

                sig = inspect.signature(cls.__init__)
                missing = _get_missing_params(sig, config)
                if missing:
                    raise ValueError(
                        f"Missing required parameters for dataset '{cls.__name__}': {', '.join(sorted(missing))}"
                    )

                init_params = _get_params_from_config(sig, config)
                if "connections_registry" in sig.parameters:
                    init_params["connections_registry"] = self.context.connections_registry if self.context else {}
                if "context" in sig.parameters:
                    init_params["context"] = self.context

                self.inner = cls(**init_params)

            def __iter__(self) -> Iterator[Dict[str, Any]]:
                return iter(self.inner)

            def __len__(self) -> int:
                return len(self.inner)

        DatasetWrapper.__name__ = cls.__name__
        DatasetWrapper.__doc__ = cls.__doc__
        DatasetWrapper.__module__ = cls.__module__
        DatasetWrapper.__qualname__ = cls.__qualname__

        DATASET_REGISTRY[dataset_name] = DatasetWrapper
        return DatasetWrapper  # type: ignore[return-value]

    return decorator


# Backward compatibility aliases
METRIC_REGISTRY = EVALUATOR_REGISTRY
BaseMetric = BaseEvaluator
metric = evaluator
