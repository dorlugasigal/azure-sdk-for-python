"""Built-in dataset loaders for common formats.

Each loader is registered via the ``@dataset`` decorator so that
:class:`~.dataset_factory.DatasetFactory` and :data:`DATASET_REGISTRY` can
resolve them by name.
"""
from __future__ import annotations

import csv as _csv_mod
import json
import logging
import os
from typing import Any, Dict, Iterator, List

from .decorators import dataset, BaseDataset

logger = logging.getLogger(__name__)


def _validate_file(path: str, expected_ext: str) -> str:
    """Validate that *path* exists and has the expected extension.

    :returns: The validated path.
    :raises FileNotFoundError: If the file does not exist.
    :raises ValueError: If the extension does not match.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Dataset file not found: {path}. "
            f"Please verify the 'data_path' in your dataset configuration."
        )
    _, ext = os.path.splitext(path)
    if ext.lower() != expected_ext:
        logger.warning(
            "Dataset file '%s' does not have expected extension '%s'",
            path,
            expected_ext,
        )
    return path


@dataset(name="jsonl")
class JsonlDataset(BaseDataset):
    """Load dataset from a JSONL (JSON Lines) file.

    Each non-empty line in the file is parsed as a JSON object and yielded as a
    ``dict``.  The file is read lazily on first iteration and cached for
    subsequent passes.
    """

    def __init__(self, data_path: str = "", **kwargs: Any) -> None:
        super().__init__()
        self.data_path = data_path
        self._records: List[Dict[str, Any]] = []
        self._loaded = False
        if data_path:
            _validate_file(data_path, ".jsonl")

    def _load(self) -> None:
        """Read all records from the JSONL file into memory."""
        if self._loaded or not self.data_path:
            return
        records: List[Dict[str, Any]] = []
        with open(self.data_path, "r", encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON on line {line_no} of {self.data_path}: {exc}"
                    ) from exc
        self._records = records
        self._loaded = True
        logger.debug("Loaded %d records from %s", len(self._records), self.data_path)

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        self._load()
        return iter(self._records)

    def __len__(self) -> int:
        self._load()
        return len(self._records)


@dataset(name="csv")
class CsvDataset(BaseDataset):
    """Load dataset from a CSV file.

    Uses the stdlib :mod:`csv` module (no pandas dependency).  The first row is
    expected to contain column headers.  Records are loaded lazily on first
    iteration.
    """

    def __init__(self, data_path: str = "", **kwargs: Any) -> None:
        super().__init__()
        self.data_path = data_path
        self._records: List[Dict[str, Any]] = []
        self._loaded = False
        if data_path:
            _validate_file(data_path, ".csv")

    def _load(self) -> None:
        """Read all records from the CSV file into memory."""
        if self._loaded or not self.data_path:
            return
        with open(self.data_path, "r", encoding="utf-8", newline="") as f:
            reader = _csv_mod.DictReader(f)
            self._records = list(reader)
        self._loaded = True
        logger.debug("Loaded %d records from %s", len(self._records), self.data_path)

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        self._load()
        return iter(self._records)

    def __len__(self) -> int:
        self._load()
        return len(self._records)
