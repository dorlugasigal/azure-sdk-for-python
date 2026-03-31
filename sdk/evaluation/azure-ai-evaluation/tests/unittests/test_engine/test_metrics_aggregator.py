# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for EvaluatorsAggregator and AggregatedEvaluators."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from azure.ai.evaluation._engine.evaluators_aggregator import (
    AggregatedEvaluators,
    EvaluatorsAggregator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_evaluator_registry() -> Dict[str, MagicMock]:
    """Evaluator registry with two mock evaluators that support aggregate()."""
    accuracy = MagicMock()
    accuracy.aggregate.return_value = {"accuracy": 0.95, "f1_score": 0.92}

    relevance = MagicMock()
    relevance.aggregate.return_value = {"relevance": 0.88}

    return {"accuracy_evaluator": accuracy, "relevance_evaluator": relevance}


@pytest.fixture()
def sample_results_data() -> List[Dict[str, Any]]:
    """Two-record JSONL payload produced by the evaluation engine."""
    return [
        {
            "run_id": "test-run-123",
            "model_name": "echo-target",
            "model_display_name": "echo-target",
            "args": {"temperature": 0.7, "max_tokens": 100},
            "metadata": {"version": "1.0", "experiment": "test_exp"},
            "evaluators": {
                "accuracy_evaluator": {"accuracy": 1.0},
                "relevance_evaluator": {"relevance": 0.9},
            },
            "system_evaluators": {
                "response_time": {"response_time_ms": 150},
            },
        },
        {
            "run_id": "test-run-123",
            "model_name": "echo-target",
            "model_display_name": "echo-target",
            "args": {"temperature": 0.7, "max_tokens": 100},
            "metadata": {"version": "1.0", "experiment": "test_exp"},
            "evaluators": {
                "accuracy_evaluator": {"accuracy": 0.8},
                "relevance_evaluator": {"relevance": 0.85},
            },
            "system_evaluators": {
                "response_time": {"response_time_ms": 200},
            },
        },
    ]


@pytest.fixture()
def sample_results_with_failures() -> List[Dict[str, Any]]:
    """Results where some evaluator scores are None (failures)."""
    return [
        {
            "run_id": "test-run-456",
            "model_name": "echo-target",
            "args": {},
            "metadata": {},
            "evaluators": {
                "accuracy_evaluator": {"accuracy": 1.0},
                "relevance_evaluator": None,
            },
            "system_evaluators": {"response_time": {"response_time_ms": 100}},
        },
        {
            "run_id": "test-run-456",
            "model_name": "echo-target",
            "args": {},
            "metadata": {},
            "evaluators": {
                "accuracy_evaluator": None,
                "relevance_evaluator": None,
            },
            "system_evaluators": {"response_time": {"response_time_ms": 120}},
        },
    ]


def _write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    with open(path, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# AggregatedEvaluators
# ---------------------------------------------------------------------------


class TestAggregatedEvaluators:
    """Tests for the AggregatedEvaluators dataclass."""

    def test_to_dict(self) -> None:
        metrics = AggregatedEvaluators(
            run_id="run-1",
            aggregated_evaluators={"accuracy": 0.95},
            tags={"model_name": "gpt-4"},
        )
        result = metrics.to_dict()

        assert result["run_id"] == "run-1"
        assert result["aggregated_evaluators"] == {"accuracy": 0.95}
        assert result["tags"] == {"model_name": "gpt-4"}

    def test_to_dict_default_tags(self) -> None:
        metrics = AggregatedEvaluators(run_id="run-2", aggregated_evaluators={})
        assert metrics.to_dict()["tags"] == {}


# ---------------------------------------------------------------------------
# EvaluatorsAggregator
# ---------------------------------------------------------------------------


class TestEvaluatorsAggregator:
    """Tests for EvaluatorsAggregator."""

    def test_initialization(self, mock_evaluator_registry: Dict[str, MagicMock]) -> None:
        aggregator = EvaluatorsAggregator(mock_evaluator_registry)
        assert aggregator.evaluator_registry is mock_evaluator_registry

    # -- _add_evaluator_prefix ------------------------------------------------

    def test_add_evaluator_prefix(self) -> None:
        result = EvaluatorsAggregator._add_evaluator_prefix(
            "accuracy", {"score": 0.95, "f1": 0.9, "label": "good"}
        )
        assert result == {"accuracy - score": 0.95, "accuracy - f1": 0.9}
        assert "accuracy - label" not in result  # non-numeric filtered

    def test_add_evaluator_prefix_empty(self) -> None:
        assert EvaluatorsAggregator._add_evaluator_prefix("x", {}) == {}

    # -- analyze_results: success path ----------------------------------------

    def test_analyze_results_success(
        self,
        tmp_path: Path,
        mock_evaluator_registry: Dict[str, MagicMock],
        sample_results_data: List[Dict[str, Any]],
    ) -> None:
        results_file = tmp_path / "results.jsonl"
        _write_jsonl(results_file, sample_results_data)

        aggregator = EvaluatorsAggregator(mock_evaluator_registry)
        result = aggregator.analyze_results(results_file)

        assert result.run_id == "test-run-123"
        assert result.aggregated_evaluators["number_of_records"] == 2

        # Each evaluator's aggregate() was called once
        mock_evaluator_registry["accuracy_evaluator"].aggregate.assert_called_once()
        mock_evaluator_registry["relevance_evaluator"].aggregate.assert_called_once()

        # Prefixed metrics present
        assert "accuracy_evaluator - accuracy" in result.aggregated_evaluators
        assert "accuracy_evaluator - f1_score" in result.aggregated_evaluators
        assert "relevance_evaluator - relevance" in result.aggregated_evaluators

    def test_analyze_results_tags_from_first_record(
        self,
        tmp_path: Path,
        mock_evaluator_registry: Dict[str, MagicMock],
        sample_results_data: List[Dict[str, Any]],
    ) -> None:
        results_file = tmp_path / "results.jsonl"
        _write_jsonl(results_file, sample_results_data)

        aggregator = EvaluatorsAggregator(mock_evaluator_registry)
        result = aggregator.analyze_results(results_file)

        assert result.tags["temperature"] == 0.7
        assert result.tags["target_name"] == "echo-target"
        assert result.tags["version"] == "1.0"

    def test_analyze_results_response_time(
        self,
        tmp_path: Path,
        mock_evaluator_registry: Dict[str, MagicMock],
        sample_results_data: List[Dict[str, Any]],
    ) -> None:
        results_file = tmp_path / "results.jsonl"
        _write_jsonl(results_file, sample_results_data)

        aggregator = EvaluatorsAggregator(mock_evaluator_registry)
        result = aggregator.analyze_results(results_file)

        expected_avg = int((150 + 200) / 2)
        assert result.aggregated_evaluators["average_response_time_ms"] == expected_avg

    # -- analyze_results: failures --------------------------------------------

    def test_analyze_results_with_failures(
        self,
        tmp_path: Path,
        mock_evaluator_registry: Dict[str, MagicMock],
        sample_results_with_failures: List[Dict[str, Any]],
    ) -> None:
        results_file = tmp_path / "results.jsonl"
        _write_jsonl(results_file, sample_results_with_failures)

        aggregator = EvaluatorsAggregator(mock_evaluator_registry)
        result = aggregator.analyze_results(results_file)

        assert result.aggregated_evaluators["accuracy_evaluator - Fail count"] == 1
        assert result.aggregated_evaluators["relevance_evaluator - Fail count"] == 2

    def test_analyze_results_all_none_skips_aggregation(
        self,
        tmp_path: Path,
    ) -> None:
        """When every score for an evaluator is None, aggregate() is never called."""
        records = [
            {
                "run_id": "r1",
                "model_name": "m",
                "args": {},
                "metadata": {},
                "evaluators": {"eval_a": None},
                "system_evaluators": {},
            },
        ]
        results_file = tmp_path / "results.jsonl"
        _write_jsonl(results_file, records)

        mock_eval = MagicMock()
        aggregator = EvaluatorsAggregator({"eval_a": mock_eval})
        result = aggregator.analyze_results(results_file)

        mock_eval.aggregate.assert_not_called()
        assert result.aggregated_evaluators["eval_a - Fail count"] == 1

    # -- analyze_results: evaluator not in registry ---------------------------

    def test_analyze_results_evaluator_not_in_registry(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        records = [
            {
                "run_id": "r1",
                "model_name": "m",
                "args": {},
                "metadata": {},
                "evaluators": {"unknown_evaluator": {"score": 1.0}},
                "system_evaluators": {},
            },
        ]
        results_file = tmp_path / "results.jsonl"
        _write_jsonl(results_file, records)

        aggregator = EvaluatorsAggregator({})
        with caplog.at_level("WARNING"):
            result = aggregator.analyze_results(results_file)

        assert "unknown_evaluator" in caplog.text
        assert "not found in registry" in caplog.text

    # -- analyze_results: aggregation failure ---------------------------------

    def test_analyze_results_aggregation_exception(
        self,
        tmp_path: Path,
    ) -> None:
        records = [
            {
                "run_id": "r1",
                "model_name": "m",
                "args": {},
                "metadata": {},
                "evaluators": {"bad_eval": {"score": 1.0}},
                "system_evaluators": {},
            },
        ]
        results_file = tmp_path / "results.jsonl"
        _write_jsonl(results_file, records)

        bad_eval = MagicMock()
        bad_eval.aggregate.side_effect = RuntimeError("boom")

        aggregator = EvaluatorsAggregator({"bad_eval": bad_eval})
        result = aggregator.analyze_results(results_file)

        # Fallback marker emitted
        assert result.aggregated_evaluators.get("bad_eval - Aggregation Failed") == -1

    # -- analyze_results: edge cases ------------------------------------------

    def test_analyze_results_empty_file(self, tmp_path: Path) -> None:
        results_file = tmp_path / "empty.jsonl"
        results_file.write_text("")

        aggregator = EvaluatorsAggregator({})
        result = aggregator.analyze_results(results_file)

        assert result.aggregated_evaluators["number_of_records"] == 0
        assert result.aggregated_evaluators["average_response_time_ms"] == 0
        assert result.run_id == ""

    def test_analyze_results_file_not_found(self, tmp_path: Path) -> None:
        aggregator = EvaluatorsAggregator({})
        with pytest.raises(FileNotFoundError):
            aggregator.analyze_results(tmp_path / "nonexistent.jsonl")

    def test_analyze_results_invalid_json(self, tmp_path: Path) -> None:
        results_file = tmp_path / "bad.jsonl"
        results_file.write_text("not valid json\n")

        aggregator = EvaluatorsAggregator({})
        with pytest.raises(json.JSONDecodeError):
            aggregator.analyze_results(results_file)

    # -- analyze_results: legacy "metrics" key --------------------------------

    def test_analyze_results_uses_metrics_fallback_key(
        self,
        tmp_path: Path,
    ) -> None:
        """Engine emits 'evaluators' but also supports legacy 'metrics' key."""
        records = [
            {
                "run_id": "r1",
                "model_name": "m",
                "args": {},
                "metadata": {},
                "metrics": {"legacy_eval": {"score": 0.9}},
                "system_metrics": {"response_time": {"response_time_ms": 50}},
            },
        ]
        results_file = tmp_path / "results.jsonl"
        _write_jsonl(results_file, records)

        mock_eval = MagicMock()
        mock_eval.aggregate.return_value = {"score": 0.9}

        aggregator = EvaluatorsAggregator({"legacy_eval": mock_eval})
        result = aggregator.analyze_results(results_file)

        mock_eval.aggregate.assert_called_once()
        assert result.aggregated_evaluators["legacy_eval - score"] == 0.9
        assert result.aggregated_evaluators["average_response_time_ms"] == 50
