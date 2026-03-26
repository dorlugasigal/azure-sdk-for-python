"""Dataset factory for creating dataset instances based on type."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, Optional

from .decorators import DATASET_REGISTRY, BaseDataset

if TYPE_CHECKING:
    from .config import DatasetConfig
    from .models import ExecutionContext

logger = logging.getLogger(__name__)

# Built-in dataset types that ship with the engine
BUILTIN_DATASET_TYPES: FrozenSet[str] = frozenset({"csv", "jsonl"})

# File-extension to dataset-type mapping for auto-detection
_EXTENSION_TO_TYPE: Dict[str, str] = {
    ".csv": "csv",
    ".jsonl": "jsonl",
}


def _ensure_builtin_datasets() -> None:
    """Import built-in datasets to trigger @dataset registration."""
    if not BUILTIN_DATASET_TYPES.intersection(DATASET_REGISTRY):
        from . import datasets as _datasets  # noqa: F401


class DatasetFactory:
    """Factory for creating dataset instances via the registry.

    Supports:
    - Built-in types (csv, jsonl) looked up by type name
    - Custom datasets looked up by dataset name in the registry
    - Path overrides (e.g. mounted Azure paths)
    - Auto type detection from file extension
    """

    def create_from_config(
        self,
        dataset_config: "DatasetConfig",
        dataset_path_override: Optional[str] = None,
        context: Optional["ExecutionContext"] = None,
    ) -> BaseDataset:
        """Create a dataset from a DatasetConfig, handling type routing and path overrides.

        :param dataset_config: Dataset configuration from the experiment config.
        :param dataset_path_override: Optional path that overrides ``data_path`` in args
            (e.g. a mounted path from Azure ML).
        :param context: Optional execution context with experiment info.
        :returns: A ``BaseDataset`` instance ready for iteration.
        """
        _ensure_builtin_datasets()
        ds_type = dataset_config.type
        args: Dict[str, Any] = dict(dataset_config.args or {})

        if dataset_path_override is not None:
            if ds_type == "custom":
                # Custom datasets keep their type; just override the path
                args["data_path"] = dataset_path_override
            else:
                # Built-in datasets: re-detect type from new path extension
                ds_type = _detect_type_from_path(dataset_path_override)
                args = {"data_path": dataset_path_override}

        return self.create_dataset(
            dataset_type=ds_type,
            args=args,
            context=context,
            dataset_name=dataset_config.name,
        )

    def create_dataset(
        self,
        dataset_type: str,
        args: Optional[Dict[str, Any]] = None,
        context: Optional["ExecutionContext"] = None,
        dataset_name: Optional[str] = None,
    ) -> BaseDataset:
        """Create a dataset instance by looking up the type in the registry.

        :param dataset_type: Type of the dataset (e.g. ``'csv'``, ``'jsonl'``, ``'custom'``).
        :param args: Configuration arguments forwarded to the dataset constructor.
        :param context: Optional execution context.
        :param dataset_name: Registry name for custom datasets.
        :returns: A ``BaseDataset`` instance.
        :raises ValueError: If the dataset type or name is not found.
        """
        args = args or {}

        # Route to the correct registry key
        if dataset_type in BUILTIN_DATASET_TYPES:
            lookup_key = dataset_type
        elif dataset_type == "custom":
            if not dataset_name:
                raise ValueError(
                    f"'dataset_name' is required for custom dataset type. "
                    f"Built-in types are: {sorted(BUILTIN_DATASET_TYPES)}."
                )
            lookup_key = dataset_name
        else:
            raise ValueError(
                f"Unsupported dataset type '{dataset_type}'. "
                f"Built-in types are: {sorted(BUILTIN_DATASET_TYPES)}. "
                f"For user-defined datasets use type='custom' with a dataset_name."
            )

        dataset_class = DATASET_REGISTRY.get(lookup_key)
        if not dataset_class:
            available = sorted(DATASET_REGISTRY.keys())
            raise ValueError(
                f"Dataset '{lookup_key}' not found in registry. "
                f"Available datasets: {available}. "
                f"Ensure the dataset is decorated with @dataset(name='{lookup_key}') and imported."
            )

        logger.debug("Creating dataset '%s' (type=%s)", lookup_key, dataset_type)
        return dataset_class(args, context)


def _detect_type_from_path(path: str) -> str:
    """Detect dataset type from a file path's extension.

    :param path: File path to inspect.
    :returns: Dataset type string.
    :raises ValueError: If the extension is not recognised.
    """
    import os

    _, ext = os.path.splitext(path)
    ext = ext.lower()
    ds_type = _EXTENSION_TO_TYPE.get(ext)
    if ds_type is None:
        supported = ", ".join(sorted(_EXTENSION_TO_TYPE.keys()))
        raise ValueError(
            f"Cannot auto-detect dataset type from extension '{ext}' "
            f"(path: {path}). Supported extensions: {supported}."
        )
    return ds_type
