# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for dataset loading (JSONL, CSV) and DatasetFactory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from azure.ai.evaluation._engine.datasets import CsvDataset, JsonlDataset
from azure.ai.evaluation._engine.dataset_factory import (
    BUILTIN_DATASET_TYPES,
    DatasetFactory,
)
from azure.ai.evaluation._engine.decorators import BaseDataset


# ---------------------------------------------------------------------------
# Helper — datasets are wrapped by @dataset decorator, so the public
# constructor takes (config: dict, context) rather than keyword args.
# ---------------------------------------------------------------------------

def _make_jsonl(path: str) -> BaseDataset:
    """Instantiate JsonlDataset through its wrapper interface."""
    return JsonlDataset({"data_path": path}, None)


def _make_csv(path: str) -> BaseDataset:
    """Instantiate CsvDataset through its wrapper interface."""
    return CsvDataset({"data_path": path}, None)


# ---------------------------------------------------------------------------
# JsonlDataset
# ---------------------------------------------------------------------------

class TestJsonlDataset:
    """Tests for JsonlDataset."""

    def test_load_valid_file(self, temp_jsonl_file: Path) -> None:
        ds = _make_jsonl(str(temp_jsonl_file))
        assert len(ds) == 5

    def test_iteration(self, temp_jsonl_file: Path) -> None:
        ds = _make_jsonl(str(temp_jsonl_file))
        records = list(ds)
        assert records[0]["question"] == "What is AI?"
        assert records[0]["expected"] == "Artificial Intelligence"

    def test_multiple_iterations_consistent(self, temp_jsonl_file: Path) -> None:
        ds = _make_jsonl(str(temp_jsonl_file))
        first = list(ds)
        second = list(ds)
        assert first == second

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="Dataset file not found"):
            _make_jsonl("/nonexistent/data.jsonl")

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.jsonl"
        bad.write_text('{"valid": true}\n{invalid json}\n')
        ds = _make_jsonl(str(bad))
        with pytest.raises(ValueError, match="Invalid JSON on line 2"):
            list(ds)

    def test_empty_lines_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "gaps.jsonl"
        f.write_text('{"a": 1}\n\n{"b": 2}\n\n')
        ds = _make_jsonl(str(f))
        assert len(ds) == 2

    def test_unicode_data(self, tmp_path: Path) -> None:
        f = tmp_path / "unicode.jsonl"
        f.write_text(json.dumps({"text": "日本語テスト 🚀"}) + "\n")
        ds = _make_jsonl(str(f))
        records = list(ds)
        assert records[0]["text"] == "日本語テスト 🚀"

    def test_no_data_path_empty_dataset(self) -> None:
        ds = _make_jsonl("")
        assert len(ds) == 0
        assert list(ds) == []


# ---------------------------------------------------------------------------
# CsvDataset
# ---------------------------------------------------------------------------

class TestCsvDataset:
    """Tests for CsvDataset."""

    def test_load_valid_file(self, temp_csv_file: Path) -> None:
        ds = _make_csv(str(temp_csv_file))
        assert len(ds) == 5

    def test_iteration(self, temp_csv_file: Path) -> None:
        ds = _make_csv(str(temp_csv_file))
        records = list(ds)
        assert records[0]["question"] == "What is AI?"
        assert records[0]["expected"] == "Artificial Intelligence"

    def test_multiple_iterations_consistent(self, temp_csv_file: Path) -> None:
        ds = _make_csv(str(temp_csv_file))
        first = list(ds)
        second = list(ds)
        assert first == second

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="Dataset file not found"):
            _make_csv("/nonexistent/data.csv")

    def test_empty_csv(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.csv"
        f.write_text("")
        ds = _make_csv(str(f))
        assert len(ds) == 0

    def test_unicode_csv(self, tmp_path: Path) -> None:
        f = tmp_path / "unicode.csv"
        f.write_text("text,label\n世界,hello\n🚀,rocket\n")
        ds = _make_csv(str(f))
        records = list(ds)
        assert records[0]["text"] == "世界"
        assert records[1]["text"] == "🚀"

    def test_no_data_path_empty_dataset(self) -> None:
        ds = _make_csv("")
        assert len(ds) == 0
        assert list(ds) == []


# ---------------------------------------------------------------------------
# DatasetFactory
# ---------------------------------------------------------------------------

class TestDatasetFactory:
    """Tests for DatasetFactory type routing."""

    def test_create_jsonl_dataset(self, temp_jsonl_file: Path) -> None:
        factory = DatasetFactory()
        ds = factory.create_dataset(
            dataset_type="jsonl",
            args={"data_path": str(temp_jsonl_file)},
        )
        assert isinstance(ds, BaseDataset)
        assert len(ds) == 5

    def test_create_csv_dataset(self, temp_csv_file: Path) -> None:
        factory = DatasetFactory()
        ds = factory.create_dataset(
            dataset_type="csv",
            args={"data_path": str(temp_csv_file)},
        )
        assert isinstance(ds, BaseDataset)
        assert len(ds) == 5

    def test_unsupported_type_raises(self) -> None:
        factory = DatasetFactory()
        with pytest.raises(ValueError, match="Unsupported dataset type"):
            factory.create_dataset(dataset_type="xml")

    def test_custom_type_without_name_raises(self) -> None:
        factory = DatasetFactory()
        with pytest.raises(ValueError, match="dataset_name.*required"):
            factory.create_dataset(dataset_type="custom")

    def test_custom_type_with_unknown_name_raises(self) -> None:
        factory = DatasetFactory()
        with pytest.raises(ValueError, match="not found in registry"):
            factory.create_dataset(
                dataset_type="custom", dataset_name="nonexistent"
            )

    def test_builtin_types_constant(self) -> None:
        assert "csv" in BUILTIN_DATASET_TYPES
        assert "jsonl" in BUILTIN_DATASET_TYPES

    def test_auto_type_detection_csv(self, temp_csv_file: Path) -> None:
        from azure.ai.evaluation._engine.config import DatasetConfig

        factory = DatasetFactory()
        cfg = DatasetConfig(name="test", type="csv", args={"data_path": str(temp_csv_file)})
        # Override path to a CSV file — type should be auto-detected
        ds = factory.create_from_config(cfg, dataset_path_override=str(temp_csv_file))
        assert isinstance(ds, BaseDataset)

    def test_auto_type_detection_jsonl(self, temp_jsonl_file: Path) -> None:
        from azure.ai.evaluation._engine.config import DatasetConfig

        factory = DatasetFactory()
        cfg = DatasetConfig(name="test", type="jsonl", args={"data_path": str(temp_jsonl_file)})
        ds = factory.create_from_config(cfg, dataset_path_override=str(temp_jsonl_file))
        assert isinstance(ds, BaseDataset)
