"""Decorators and base classes for metrics, targets, and datasets."""
from __future__ import annotations

import asyncio
import inspect
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from numbers import Number
from typing import Any, Dict, List, Optional, TypeVar, cast

from .models import ExecutionContext, InferenceOutput

T = TypeVar("T")

# Global registries
EVALUATOR_REGISTRY: Dict[str, type] = {}
TARGET_REGISTRY: Dict[str, type] = {}
DATASET_REGISTRY: Dict[str, type] = {}


# Helper functions — imported from dedicated module (see decorator_helpers.py)
from .decorator_helpers import get_missing_params as _get_missing_params
from .decorator_helpers import get_params_from_config as _get_params_from_config


# Base classes
class BaseEvaluator(ABC):
    """Base class for all evaluators."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, context: Optional[ExecutionContext] = None):
        config = config or {}
        self.name = config.get("name", self.__class__.__name__)
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
        """Map fields from inference output to evaluator inputs."""
        data = inference_output.to_dict()
        output = data.get("output", {})
        sources = {"model": output, "target": output, "dataset": data.get("record", {})}

        mapped_fields = {}
        for param, mapping in self.mapping.items():
            source, field = mapping.split(".", 1)
            value = sources.get(source, {}).get(field)
            if value is None:
                # Optional fields (e.g., tool_definitions) may not be present
                # for all targets — use empty list/string as fallback
                if field in ("tool_definitions", "tool_calls"):
                    mapped_fields[param] = []
                else:
                    raise KeyError(
                        f"Field '{field}' not found in '{source}'. "
                        f"Please verify mapping for metric '{self.display_name}'"
                    )
            else:
                mapped_fields[param] = value
        return mapped_fields


class BaseTarget(ABC):
    """Base class for all targets."""

    def __init__(self, context: Optional[ExecutionContext] = None):
        self.context = context

    @abstractmethod
    def infer(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Perform inference on input.

        Override with ``def infer(...)`` for synchronous targets or
        ``async def infer(...)`` for asynchronous targets.
        """
        ...

    def close(self) -> None:
        """Optional cleanup method. Override to release resources."""
        pass

    async def close_async(self) -> None:
        """Async interface for cleanup."""
        pass


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
                    pattern = re.compile(r"^(target|model|dataset)\.[^\.]+$")
                    for field, mapping_val in self.mapping.items():
                        if not pattern.match(mapping_val):
                            raise ValueError(
                                f"Invalid mapping '{mapping_val}' for field '{field}' in evaluator '{self.name}': "
                                f"expected format 'target.X' or 'dataset.X'"
                            )

                # Create inner metric instance — pass config values + extra kwargs
                cls_sig = inspect.signature(cls.__init__)
                cloud = self.context.cloud_config if self.context else None
                init_params: Dict[str, Any] = {}
                for param_name_inner, param in cls_sig.parameters.items():
                    if param_name_inner == "self":
                        continue
                    if param_name_inner == "context":
                        init_params[param_name_inner] = self.context
                    elif param_name_inner == "cloud_config":
                        init_params[param_name_inner] = cloud
                    elif param_name_inner == "azure_endpoint":
                        init_params[param_name_inner] = cloud.foundry_endpoint if cloud else None
                    elif param_name_inner == "deployment_name":
                        init_params[param_name_inner] = (
                            config.get("deployment_name")
                            or (cloud.default_evaluator_deployment if cloud else None)
                        )
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


def _validate_infer(cls: type) -> None:
    """Ensure *cls* provides a concrete ``infer`` method.

    Raises :class:`NotImplementedError` at decoration time with actionable
    guidance instead of letting the cryptic ``TypeError: Can't instantiate
    abstract class …`` surface at runtime.
    """
    # For plain classes (no ABC), missing `infer` will already raise
    # AttributeError on the `inspect.iscoroutinefunction(cls.infer)` call
    # that follows — no extra check needed.
    abstract_methods = getattr(cls, "__abstractmethods__", None)
    if abstract_methods is None or "infer" not in abstract_methods:
        return

    raise NotImplementedError(
        f"Target class '{cls.__name__}' must implement the 'infer' method. "
        f"Use either 'def infer(self, input)' for sync targets or "
        f"'async def infer(self, input)' for async targets."
    )


def target(name: Optional[str] = None) -> Callable[[type[T]], type[T]]:
    """Decorator for creating targets."""

    def decorator(cls: type[T]) -> type[T]:
        target_name = name if name is not None else cls.__name__

        if target_name in TARGET_REGISTRY:
            raise ValueError(f"Target '{target_name}' already registered")

        # Validate that the user provided a concrete infer() implementation.
        # BaseTarget.infer is abstract; the user must override it with either
        # ``def infer(...)`` or ``async def infer(...)``.
        _validate_infer(cls)

        # Detect if the user's infer method is async
        is_async = inspect.iscoroutinefunction(cls.infer)

        class TargetWrapper(BaseTarget):
            def __init__(self, config: Dict[str, Any], context: Optional[ExecutionContext] = None):
                super().__init__(context)

                cls_sig = inspect.signature(cls.__init__)
                missing = _get_missing_params(cls_sig, config)
                if missing:
                    raise ValueError(f"Missing required parameters for target '{cls.__name__}': {', '.join(missing)}")

                init_params = _get_params_from_config(cls_sig, config)
                if "context" in cls_sig.parameters:
                    init_params["context"] = self.context

                self.inner = cls(**init_params)
                self._is_async = is_async
                self._has_close = hasattr(cls, "close") and callable(cls.close)
                self._close_is_async = self._has_close and inspect.iscoroutinefunction(cls.close)

            def infer(self, input: Dict[str, Any]) -> Dict[str, Any]:
                """Sync interface — works for both sync and async targets.

                - Sync targets: direct call
                - Async targets: runs in new event loop via asyncio.run()
                """
                if self._is_async:
                    return asyncio.run(self.inner.infer(input))
                return self.inner.infer(input)

            async def infer_async(self, input: Dict[str, Any]) -> Dict[str, Any]:
                """Async interface — works for both sync and async targets.

                - Async targets: direct await
                - Sync targets: runs in thread pool executor to avoid blocking
                """
                if self._is_async:
                    return await self.inner.infer(input)
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, self.inner.infer, input)

            def close(self) -> None:
                """Sync cleanup — handles both sync and async close methods."""
                if not self._has_close:
                    return
                if self._close_is_async:
                    asyncio.run(self.inner.close())
                else:
                    self.inner.close()

            async def close_async(self) -> None:
                """Async cleanup — handles both sync and async close methods."""
                if not self._has_close:
                    return
                if self._close_is_async:
                    await self.inner.close()
                else:
                    self.inner.close()

        TargetWrapper.__name__ = cls.__name__
        TargetWrapper.__doc__ = cls.__doc__
        TargetWrapper.__module__ = cls.__module__
        TargetWrapper.__qualname__ = cls.__qualname__

        TARGET_REGISTRY[target_name] = TargetWrapper
        return cast(type[T], TargetWrapper)

    return decorator


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
