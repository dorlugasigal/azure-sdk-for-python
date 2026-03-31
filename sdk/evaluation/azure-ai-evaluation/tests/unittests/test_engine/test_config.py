# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for the engine configuration models."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from azure.ai.evaluation._engine.models.config import (
    Config,
    ComputeConfig,
    ConnectionConfig,
    DatasetConfig,
    EvaluatorConfig,
    ExperimentConfig,
    TargetVariantConfig,
    _resolve_env_vars,
)


# ---------------------------------------------------------------------------
# _resolve_env_vars
# ---------------------------------------------------------------------------

class TestResolveEnvVars:
    """Tests for POSIX-style environment variable interpolation."""

    def test_required_var_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_VAR", "hello")
        assert _resolve_env_vars("${MY_VAR}") == "hello"

    def test_required_var_unset_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNSET_VAR", raising=False)
        with pytest.raises(ValueError, match="Missing required env var"):
            _resolve_env_vars("${UNSET_VAR}")

    def test_colon_dash_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPT_VAR", raising=False)
        assert _resolve_env_vars("${OPT_VAR:-fallback}") == "fallback"

    def test_colon_dash_default_when_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPT_VAR", "")
        assert _resolve_env_vars("${OPT_VAR:-fallback}") == "fallback"

    def test_colon_dash_uses_value_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPT_VAR", "actual")
        assert _resolve_env_vars("${OPT_VAR:-fallback}") == "actual"

    def test_dash_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPT_VAR", raising=False)
        assert _resolve_env_vars("${OPT_VAR-fallback}") == "fallback"

    def test_dash_preserves_empty_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPT_VAR", "")
        assert _resolve_env_vars("${OPT_VAR-fallback}") == ""

    def test_multiple_vars_in_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "8080")
        assert _resolve_env_vars("http://${HOST}:${PORT}") == "http://localhost:8080"

    def test_no_env_vars(self) -> None:
        assert _resolve_env_vars("plain string") == "plain string"

    def test_empty_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("X", raising=False)
        assert _resolve_env_vars("${X:-}") == ""


# ---------------------------------------------------------------------------
# Config.from_yaml / from_dict
# ---------------------------------------------------------------------------

class TestConfig:
    """Tests for Config root model."""

    def test_from_dict_minimal(self) -> None:
        cfg = Config.from_dict({"experiment": {"name": "test"}})
        assert cfg.experiment.name == "test"
        assert cfg.experiment.version == "1.0"

    def test_from_dict_full(self, mock_config_dict: Dict[str, Any]) -> None:
        cfg = Config.from_dict(mock_config_dict)
        assert cfg.experiment.name == "test-experiment"
        assert cfg.experiment.max_workers == 2
        assert cfg.experiment.dataset.type == "jsonl"
        assert len(cfg.experiment.targets) == 1
        assert len(cfg.experiment.evaluators) == 1

    def test_from_yaml(self, mock_config_yaml: Path) -> None:
        cfg = Config.from_yaml(str(mock_config_yaml))
        assert cfg.experiment.name == "test-experiment"

    def test_from_yaml_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            Config.from_yaml("/nonexistent/config.yaml")

    def test_from_yaml_empty_file(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        with pytest.raises(ValueError, match="empty"):
            Config.from_yaml(str(empty))

    def test_from_yaml_comments_only(self, tmp_path: Path) -> None:
        comments = tmp_path / "comments.yaml"
        comments.write_text("# just a comment\n# another comment\n")
        with pytest.raises(ValueError, match="empty"):
            Config.from_yaml(str(comments))

    def test_to_dict(self, mock_config_dict: Dict[str, Any]) -> None:
        cfg = Config.from_dict(mock_config_dict)
        d = cfg.to_dict()
        assert d["experiment"]["name"] == "test-experiment"

    def test_env_var_interpolation_in_yaml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EXP_NAME", "from-env")
        yaml_content = {"experiment": {"name": "${EXP_NAME}"}}
        p = tmp_path / "env.yaml"
        p.write_text(yaml.dump(yaml_content))
        cfg = Config.from_yaml(str(p))
        assert cfg.experiment.name == "from-env"

    def test_validation_error_missing_experiment(self) -> None:
        with pytest.raises(Exception):
            Config.from_dict({})

    def test_validation_error_missing_experiment_name(self) -> None:
        with pytest.raises(Exception):
            Config.from_dict({"experiment": {}})


# ---------------------------------------------------------------------------
# deep_validate
# ---------------------------------------------------------------------------

class TestDeepValidate:
    """Tests for Config.deep_validate() registry checks."""

    def test_deep_validate_empty_config(self) -> None:
        cfg = Config.from_dict({"experiment": {"name": "test"}})
        errors = cfg.deep_validate()
        assert errors == []

    def test_deep_validate_missing_target(self) -> None:
        cfg = Config.from_dict({
            "experiment": {
                "name": "test",
                "targets": [{"name": "nonexistent", "type": "custom"}],
            }
        })
        errors = cfg.deep_validate()
        assert any("nonexistent" in e for e in errors)

    def test_deep_validate_missing_evaluator(self) -> None:
        cfg = Config.from_dict({
            "experiment": {
                "name": "test",
                "evaluators": [{"name": "nonexistent"}],
            }
        })
        errors = cfg.deep_validate()
        assert any("nonexistent" in e for e in errors)


# ---------------------------------------------------------------------------
# EvaluatorConfig mapping validation
# ---------------------------------------------------------------------------

class TestMappingValidation:
    """Tests for EvaluatorConfig mapping format validation."""

    def test_valid_mapping(self) -> None:
        ec = EvaluatorConfig(
            name="test",
            mapping={"question": "dataset.question", "answer": "target.answer"},
        )
        assert ec.mapping["question"] == "dataset.question"

    def test_invalid_mapping_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid mapping"):
            EvaluatorConfig(name="test", mapping={"field": "bad_format"})

    def test_model_prefix_mapping(self) -> None:
        ec = EvaluatorConfig(name="test", mapping={"x": "model.output"})
        assert ec.mapping["x"] == "model.output"

    def test_empty_mapping_is_valid(self) -> None:
        ec = EvaluatorConfig(name="test", mapping={})
        assert ec.mapping == {}


# ---------------------------------------------------------------------------
# TargetVariantConfig validation
# ---------------------------------------------------------------------------

class TestTargetVariantConfig:
    """Tests for TargetVariantConfig type validation."""

    def test_valid_custom_type(self) -> None:
        t = TargetVariantConfig(name="t", type="custom")
        assert t.type == "custom"

    def test_valid_azure_ai_model_type(self) -> None:
        t = TargetVariantConfig(name="t", type="azure_ai_model")
        assert t.type == "azure_ai_model"

    def test_valid_azure_ai_agent_type(self) -> None:
        t = TargetVariantConfig(name="t", type="azure_ai_agent")
        assert t.type == "azure_ai_agent"

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid target type"):
            TargetVariantConfig(name="t", type="unknown")

    def test_args_dict_normalized_to_list(self) -> None:
        t = TargetVariantConfig(name="t", args={"key": "val"})
        assert isinstance(t.args, list)


# ---------------------------------------------------------------------------
# Backward-compatibility aliases
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    """Tests for backward-compatibility aliases in config."""

    def test_models_alias_for_targets(self) -> None:
        cfg = Config.from_dict({
            "experiment": {
                "name": "test",
                "models": [{"name": "m", "type": "custom"}],
            }
        })
        assert len(cfg.experiment.targets) == 1
        assert cfg.experiment.targets[0].name == "m"

    def test_metrics_alias_for_evaluators(self) -> None:
        cfg = Config.from_dict({
            "experiment": {
                "name": "test",
                "metrics": [{"name": "acc"}],
            }
        })
        assert len(cfg.experiment.evaluators) == 1
        assert cfg.experiment.evaluators[0].name == "acc"
