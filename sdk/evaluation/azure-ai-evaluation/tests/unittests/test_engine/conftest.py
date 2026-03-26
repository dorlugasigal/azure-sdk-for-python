# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Shared fixtures for azure-ai-evaluation engine tests.

Adapted from the evee test suite to match the engine's Pydantic config
models, dataclass result types, and global registries.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import click.testing
import pytest
import yaml

from azure.ai.evaluation._engine.decorators import (
    DATASET_REGISTRY,
    EVALUATOR_REGISTRY,
    TARGET_REGISTRY,
)
from azure.ai.evaluation._engine.models import InferenceOutput

# ---------------------------------------------------------------------------
# Environment — disable Rich output for deterministic test output
# ---------------------------------------------------------------------------
os.environ["AZURE_AI_EVAL_DISABLE_RICH"] = "true"


# ---------------------------------------------------------------------------
# Pytest markers
# ---------------------------------------------------------------------------
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "engine: marks engine-specific tests")


# ---------------------------------------------------------------------------
# Registry isolation
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clean_registries():
    """Snapshot and restore the global registries between tests."""
    evaluator_snapshot = dict(EVALUATOR_REGISTRY)
    target_snapshot = dict(TARGET_REGISTRY)
    dataset_snapshot = dict(DATASET_REGISTRY)
    yield
    EVALUATOR_REGISTRY.clear()
    EVALUATOR_REGISTRY.update(evaluator_snapshot)
    TARGET_REGISTRY.clear()
    TARGET_REGISTRY.update(target_snapshot)
    DATASET_REGISTRY.clear()
    DATASET_REGISTRY.update(dataset_snapshot)


# ---------------------------------------------------------------------------
# Configuration fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def mock_config_dict() -> Dict[str, Any]:
    """Complete experiment configuration dictionary (YAML-compatible)."""
    return {
        "experiment": {
            "name": "test-experiment",
            "version": "1.0",
            "description": "Unit test experiment",
            "output_path": "output",
            "max_workers": 2,
            "dataset": {
                "name": "test-dataset",
                "type": "jsonl",
                "version": "1.0.0",
                "args": {"path": "data/test.jsonl"},
            },
            "connections": [
                {
                    "name": "default",
                    "api_key": "test-key",
                    "endpoint": "https://test.openai.azure.com",
                }
            ],
            "targets": [
                {
                    "name": "echo-target",
                    "type": "custom",
                    "connection_name": "default",
                    "args": [{"temperature": 0.7}],
                }
            ],
            "evaluators": [
                {
                    "name": "relevance",
                    "mapping": {
                        "question": "dataset.question",
                        "answer": "target.answer",
                    },
                }
            ],
            "compute": {"type": "local"},
        }
    }


@pytest.fixture()
def mock_config_yaml(tmp_path: Path, mock_config_dict: Dict[str, Any]) -> Path:
    """Write *mock_config_dict* to a YAML file and return its path."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(mock_config_dict, default_flow_style=False))
    return config_path


@pytest.fixture()
def mock_target_config() -> MagicMock:
    """Mocked :class:`TargetVariantConfig`."""
    cfg = MagicMock()
    cfg.name = "echo-target"
    cfg.type = "custom"
    cfg.connection_name = "default"
    cfg.args = [{"temperature": 0.7}]
    cfg.to_dict = MagicMock(
        return_value={
            "name": "echo-target",
            "type": "custom",
            "connection_name": "default",
            "args": [{"temperature": 0.7}],
        }
    )
    return cfg


@pytest.fixture()
def mock_evaluator_config() -> MagicMock:
    """Mocked :class:`EvaluatorConfig`."""
    cfg = MagicMock()
    cfg.name = "relevance"
    cfg.display_name = None
    cfg.mapping = {"question": "dataset.question", "answer": "target.answer"}
    cfg.to_dict = MagicMock(
        return_value={
            "name": "relevance",
            "mapping": {"question": "dataset.question", "answer": "target.answer"},
        }
    )
    return cfg


@pytest.fixture()
def mock_connections_registry() -> Dict[str, Dict[str, Any]]:
    """Dictionary of connection configurations keyed by name."""
    return {
        "default": {
            "api_key": "test-key",
            "endpoint": "https://test.openai.azure.com",
        },
        "secondary": {
            "api_key": "test-key-2",
            "endpoint": "https://test2.openai.azure.com",
        },
    }


# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def sample_record() -> Dict[str, str]:
    """Minimal dataset record for testing."""
    return {"question": "What is AI?", "expected": "Artificial Intelligence"}


@pytest.fixture()
def sample_inference_output(sample_record: Dict[str, str]) -> InferenceOutput:
    """An :class:`InferenceOutput` populated with sample data."""
    return InferenceOutput(
        output={"answer": "Artificial Intelligence is a branch of computer science."},
        model_name="echo-target",
        record=sample_record,
        args={"temperature": 0.7},
    )


# ---------------------------------------------------------------------------
# Temporary file fixtures
# ---------------------------------------------------------------------------
_TEST_RECORDS = [
    {"question": "What is AI?", "expected": "Artificial Intelligence"},
    {"question": "What is ML?", "expected": "Machine Learning"},
    {"question": "What is NLP?", "expected": "Natural Language Processing"},
    {"question": "What is CV?", "expected": "Computer Vision"},
    {"question": "What is RL?", "expected": "Reinforcement Learning"},
]


@pytest.fixture()
def temp_jsonl_file(tmp_path: Path) -> Path:
    """JSONL file with five test records."""
    fpath = tmp_path / "test_data.jsonl"
    with fpath.open("w") as f:
        for rec in _TEST_RECORDS:
            f.write(json.dumps(rec) + "\n")
    return fpath


@pytest.fixture()
def temp_csv_file(tmp_path: Path) -> Path:
    """CSV file with five test records."""
    fpath = tmp_path / "test_data.csv"
    with fpath.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["question", "expected"])
        writer.writeheader()
        writer.writerows(_TEST_RECORDS)
    return fpath


# ---------------------------------------------------------------------------
# Output / experiment directory fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def mock_output_dir(tmp_path: Path) -> Path:
    """Base experiment output directory with standard subdirectories."""
    output = tmp_path / "output"
    (output / "logs").mkdir(parents=True)
    (output / "results").mkdir(parents=True)
    (output / "artifacts").mkdir(parents=True)
    return output


@pytest.fixture()
def mock_experiment_folders(tmp_path: Path) -> Path:
    """Multiple timestamped experiment folders with logs and result files."""
    base = tmp_path / "experiments"
    for ts in ("20240101_120000", "20240102_130000", "20240103_140000"):
        run_dir = base / ts
        (run_dir / "logs").mkdir(parents=True)
        (run_dir / "results").mkdir(parents=True)

        # Dummy log
        (run_dir / "logs" / "run.log").write_text(f"Run started at {ts}\n")

        # Dummy results
        results_file = run_dir / "results" / "results.jsonl"
        results_file.write_text(
            json.dumps({"target": "echo-target", "status": "completed"}) + "\n"
        )
    return base


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------
@pytest.fixture()
def cli_runner() -> click.testing.CliRunner:
    """Click CLI test runner."""
    return click.testing.CliRunner(mix_stderr=False)
