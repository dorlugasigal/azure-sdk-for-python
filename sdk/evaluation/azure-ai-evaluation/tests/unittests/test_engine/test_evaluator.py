# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for ModelEvaluator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import yaml

from azure.ai.evaluation._engine.models import EvaluationOutput, InferenceOutput


# ---------------------------------------------------------------------------
# Patch targets (module path within the evaluator module)
# ---------------------------------------------------------------------------
_MOD = "azure.ai.evaluation._engine.evaluator"
_EXEC_MOD = "azure.ai.evaluation._engine.evaluation_executor"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_config_dict() -> Dict[str, Any]:
    """Minimal valid config dict for ModelEvaluator."""
    return {
        "experiment": {
            "name": "test-experiment",
            "version": "1.0",
            "description": "unit test",
            "output_path": "output",
            "max_workers": 1,
            "dataset": {
                "name": "test-dataset",
                "type": "jsonl",
                "version": "1.0.0",
                "args": {"path": "data/test.jsonl"},
            },
            "connections": [],
            "targets": [],
            "evaluators": [],
            "compute": {"type": "local"},
        }
    }


@pytest.fixture()
def config_yaml_path(tmp_path: Path, minimal_config_dict: Dict[str, Any]) -> Path:
    """Write config dict to YAML and return the path."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(minimal_config_dict, default_flow_style=False))
    return cfg_path


def _build_evaluator(config_path: str, **kwargs):
    """Construct a ModelEvaluator with heavy dependencies mocked out."""
    from azure.ai.evaluation._engine.evaluator import ModelEvaluator

    with (
        patch(f"{_MOD}.discover_components"),
        patch(f"{_MOD}.OTelTraceCapture") as mock_otel,
        patch(f"{_MOD}._setup_logger"),
    ):
        mock_otel_instance = MagicMock()
        mock_otel_instance.setup.return_value = False
        mock_otel.return_value = mock_otel_instance

        evaluator = ModelEvaluator(config_path=config_path, **kwargs)
        return evaluator


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestModelEvaluatorInit:
    """Tests for ModelEvaluator initialization."""

    def test_init_loads_config(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=True)

        assert evaluator.config is not None
        assert evaluator.config.experiment.name == "test-experiment"

    def test_init_load_config_only_skips_registries(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=True)

        assert not hasattr(evaluator, "targets_registry")
        assert not hasattr(evaluator, "evaluators_registry")

    def test_init_full_creates_registries(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=False)

        assert hasattr(evaluator, "targets_registry")
        assert hasattr(evaluator, "evaluators_registry")

    def test_init_missing_config_raises(self, tmp_path: Path) -> None:
        missing = str(tmp_path / "no_such_file.yaml")
        with pytest.raises(Exception):
            _build_evaluator(missing, load_config_only=True)

    def test_init_creates_experiment_dir(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=False)

        assert evaluator._current_experiment_dir.exists()
        assert "test-experiment" in str(evaluator._current_experiment_dir)


# ---------------------------------------------------------------------------
# Create experiment directory
# ---------------------------------------------------------------------------


class TestCreateExperimentDir:
    def test_directory_name_format(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=False)
        dir_name = evaluator._current_experiment_dir.name

        assert dir_name.startswith("test-experiment_v1.0__")

    def test_directory_created(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=False)
        assert evaluator._current_experiment_dir.is_dir()


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


class TestDatasetLoading:
    def test_load_dataset_no_config_raises(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=True)
        # Override config to have no dataset
        evaluator.config.experiment.dataset = None

        with pytest.raises(ValueError, match="Dataset configuration required"):
            evaluator.load_dataset()

    def test_load_dataset_delegates_to_factory(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=False)

        with patch(f"{_MOD}.DatasetFactory") as MockFactory:
            mock_factory = MagicMock()
            mock_dataset = MagicMock()
            mock_factory.create_from_config.return_value = mock_dataset
            MockFactory.return_value = mock_factory

            result = evaluator.load_dataset()
            assert result is mock_dataset
            mock_factory.create_from_config.assert_called_once()


# ---------------------------------------------------------------------------
# Target registration
# ---------------------------------------------------------------------------


class TestTargetRegistration:
    def test_no_targets_creates_passthrough(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=False)

        assert "default" in evaluator.targets_registry
        target_data = evaluator.targets_registry["default"]
        # Passthrough should return input as-is
        result = target_data["model"].infer({"question": "hello"})
        assert result == {"question": "hello"}

    def test_model_filter_excludes_targets(
        self, tmp_path: Path, minimal_config_dict: Dict[str, Any]
    ) -> None:
        minimal_config_dict["experiment"]["targets"] = [
            {"name": "target-a", "type": "custom", "args": []},
            {"name": "target-b", "type": "custom", "args": []},
        ]
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump(minimal_config_dict, default_flow_style=False))

        evaluator = _build_evaluator(
            str(cfg_path), load_config_only=False, model_filter=["target-a"]
        )

        # target-b should be excluded by filter
        assert "target-a" in evaluator.targets_registry or "default" in evaluator.targets_registry
        assert "target-b" not in evaluator.targets_registry


# ---------------------------------------------------------------------------
# Args combinations
# ---------------------------------------------------------------------------


class TestArgsCombinations:
    def test_no_args(self, config_yaml_path: Path) -> None:
        from azure.ai.evaluation._engine.combination_utils import generate_args_combinations
        from azure.ai.evaluation._engine.config import TargetVariantConfig

        cfg = TargetVariantConfig(name="test")
        result = generate_args_combinations(cfg)
        assert result == [{}]

    def test_single_arg(self, config_yaml_path: Path) -> None:
        from azure.ai.evaluation._engine.combination_utils import generate_args_combinations
        from azure.ai.evaluation._engine.config import TargetVariantConfig

        cfg = TargetVariantConfig(name="test", args=[{"temperature": [0.5, 1.0]}])
        result = generate_args_combinations(cfg)

        assert len(result) == 2
        assert {"temperature": 0.5} in result
        assert {"temperature": 1.0} in result

    def test_cartesian_product(self, config_yaml_path: Path) -> None:
        from azure.ai.evaluation._engine.combination_utils import generate_args_combinations
        from azure.ai.evaluation._engine.config import TargetVariantConfig

        cfg = TargetVariantConfig(
            name="test",
            args=[{"temperature": [0.5, 1.0]}, {"max_tokens": [100, 200]}],
        )
        result = generate_args_combinations(cfg)

        assert len(result) == 4  # 2 × 2


# ---------------------------------------------------------------------------
# Variant naming
# ---------------------------------------------------------------------------


class TestVariantNaming:
    def test_generate_variant_name_no_args(self, config_yaml_path: Path) -> None:
        from azure.ai.evaluation._engine.combination_utils import generate_variant_name

        assert generate_variant_name("model", {}) == "model"

    def test_generate_variant_name_with_args(self, config_yaml_path: Path) -> None:
        from azure.ai.evaluation._engine.combination_utils import generate_variant_name

        name = generate_variant_name("model", {"temp": 0.5, "tokens": 100})
        assert name == "model__temp=0.5_tokens=100"

    def test_simplify_names_single(self, config_yaml_path: Path) -> None:
        from azure.ai.evaluation._engine.combination_utils import simplify_combination_names

        result = simplify_combination_names("m", [{"a": 1}])
        assert len(result) == 1

    def test_simplify_names_varying_keys_only(self, config_yaml_path: Path) -> None:
        from azure.ai.evaluation._engine.combination_utils import simplify_combination_names

        combos = [
            {"prompt": "baseline", "temp": 0.7},
            {"prompt": "few_shot", "temp": 0.7},
        ]
        result = simplify_combination_names("m", combos)

        # Only "prompt" varies → names should include only prompt values
        for name in result:
            assert "prompt=" in name
            assert "temp=" not in name


# ---------------------------------------------------------------------------
# Evaluation loop
# ---------------------------------------------------------------------------


class TestEvaluationLoop:
    def test_evaluate_returns_summary(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=False)

        mock_dataset = MagicMock()
        mock_dataset.__len__ = MagicMock(return_value=2)
        mock_dataset.__iter__ = MagicMock(
            return_value=iter(
                [
                    {"question": "What is AI?"},
                    {"question": "What is ML?"},
                ]
            )
        )

        # Patch the internal evaluation methods on EvaluationExecutor
        with (
            patch(f"{_EXEC_MOD}.EvaluationExecutor.evaluate_model", return_value=0) as mock_eval,
            patch(
                f"{_EXEC_MOD}.EvaluationExecutor._aggregate_and_save_evaluators", return_value={}
            ),
        ):
            result = evaluator.evaluate(mock_dataset)

        assert result["status"] == "completed"
        assert result["models_evaluated"] >= 1

    def test_evaluate_with_errors(self, config_yaml_path: Path) -> None:
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=False)

        mock_dataset = MagicMock()
        mock_dataset.__len__ = MagicMock(return_value=2)
        mock_dataset.__iter__ = MagicMock(return_value=iter([{"q": "a"}]))

        with patch(f"{_EXEC_MOD}.EvaluationExecutor.evaluate_model", return_value=1):
            result = evaluator.evaluate(mock_dataset)

        assert result["status"] == "completed_with_errors"
        assert result["failed_records"] > 0

    def test_evaluate_persists_aitk_results(
        self,
        config_yaml_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("AITK_EVALS_JOBS_DIR", str(tmp_path / "aitk-jobs"))
        evaluator = _build_evaluator(str(config_yaml_path), load_config_only=False)

        dataset = [{"question": "hello"}]
        result = evaluator.evaluate(dataset)

        aitk_job_path = Path(result.get("aitk_job_path", ""))
        assert aitk_job_path.exists()
        assert aitk_job_path.parent == tmp_path / "aitk-jobs"
        metadata = json.loads((aitk_job_path / "job-metadata.json").read_text())
        # Extension contract: parseJobMetadata requires id, input, status
        assert metadata["id"] == aitk_job_path.name
        assert "input" in metadata
        assert "evalName" in metadata["input"]
        assert "dataset" in metadata["input"]
        assert "evaluators" in metadata["input"]
        assert metadata["input"].get("evalConfigFilePath")
        assert Path(metadata["input"]["evalConfigFilePath"]).exists()
        assert metadata["status"] == "completed"
        assert "evalResultFilePath" in metadata
        assert (aitk_job_path / "logs.txt").exists()
        aitk_consolidated = json.loads((aitk_job_path / "results.json").read_text())
        assert aitk_consolidated["evaluation_id"] == aitk_job_path.name
        assert aitk_consolidated["run_id"] == aitk_job_path.name
        assert aitk_consolidated["status"] == "completed"
        assert "rows" in aitk_consolidated
        assert "metrics" in aitk_consolidated
        assert "report_url" in aitk_consolidated
        assert "studio_url" in aitk_consolidated
        # Sidebar tree: test-results/<experiment_name>.json must be a root-level array
        sidebar_path_str = result.get('aitk_sidebar_path')
        assert sidebar_path_str is not None, 'aitk_sidebar_path missing from summary'
        sidebar_file = Path(sidebar_path_str)
        assert sidebar_file.exists()
        assert sidebar_file.parent.name == 'test-results'
        sidebar_rows = json.loads(sidebar_file.read_text())
        assert isinstance(sidebar_rows, list), 'test-results JSON must be a root-level array'
        assert len(sidebar_rows) > 0
