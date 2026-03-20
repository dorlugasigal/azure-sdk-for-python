"""Built-in dataset loaders for common formats."""
from __future__ import annotations

import json
from typing import Any, Dict, Iterator

from .decorators import dataset, BaseDataset


@dataset(name="jsonl")
class JsonlDataset(BaseDataset):
    """Load dataset from JSONL file."""

    def __init__(self, data_path: str = "", **kwargs: Any) -> None:
        super().__init__()
        self.data_path = data_path
        self._records = []
        if data_path:
            with open(data_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._records.append(json.loads(line))

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)


@dataset(name="csv")
class CsvDataset(BaseDataset):
    """Load dataset from CSV file."""

    def __init__(self, data_path: str = "", **kwargs: Any) -> None:
        super().__init__()
        self.data_path = data_path
        self._records = []
        if data_path:
            import csv
            with open(data_path, "r") as f:
                reader = csv.DictReader(f)
                self._records = list(reader)

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)
