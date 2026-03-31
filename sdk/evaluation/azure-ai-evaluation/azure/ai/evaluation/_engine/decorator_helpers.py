"""Shared helper functions for decorator implementations.

Extracted from ``decorators.py`` so they can be reused across the engine
without importing the heavy decorator/registry machinery.
"""
from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional, TypeVar

T = TypeVar("T")


def get_missing_params(
    signature: inspect.Signature,
    config: Dict[str, Any],
    ignore: Optional[List[str]] = None,
) -> set:
    """Return required parameters missing from *config*.

    Parameters with default values and ``**kwargs`` are ignored.

    Args:
        signature: Function signature to check against.
        config: Configuration dict to validate.
        ignore: Optional parameter names to skip (defaults to
            ``["connections_registry", "context"]``).
    """
    if ignore is None:
        ignore = ["connections_registry", "context"]
    required = [
        p
        for p, info in signature.parameters.items()
        if p not in ["self", "return", "args", "kwargs", *ignore]
        and info.default == inspect.Parameter.empty
        and info.kind != inspect.Parameter.VAR_KEYWORD
    ]
    return set(required) - set(config.keys())


def get_params_from_config(
    signature: inspect.Signature,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Extract parameters from *config* that exist in *signature*.

    Args:
        signature: Function signature to check against.
        config: Configuration dict.
    """
    config_params = set(config.keys())
    method_params = set(signature.parameters.keys())
    params = config_params.intersection(method_params)
    return {param: config[param] for param in params}


def validate_required_methods(
    cls: type,
    base_cls: type,
    required_methods: List[str],
) -> None:
    """Validate that *cls* implements all *required_methods*.

    Args:
        cls: The class to validate.
        base_cls: The base class to check against.
        required_methods: Method names that must be overridden.

    Raises:
        NotImplementedError: If any required method is not implemented.
    """
    for method_name in required_methods:
        if not hasattr(cls, method_name) or getattr(cls, method_name) is getattr(
            base_cls, method_name, None
        ):
            raise NotImplementedError(
                f"Class '{cls.__name__}' must implement the '{method_name}' method"
            )

