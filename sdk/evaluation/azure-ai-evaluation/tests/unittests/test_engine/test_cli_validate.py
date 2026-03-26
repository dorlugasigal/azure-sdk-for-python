# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Tests for the ``validate`` CLI command."""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import click.testing
import pytest
import yaml

from azure.ai.evaluation._engine.cli import cli

os.environ["AZURE_AI_EVAL_DISABLE_RICH"] = "true"


@pytest.fixture()
def cli_runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


@pytest.fixture()
def valid_config_path(tmp_path):
    cfg = {
        "experiment": {
            "name": "test-validate",
            "targets": [{"name": "t1", "type": "custom", "args": {"temperature": [0.7]}}],
            "dataset": {"name": "ds", "type": "jsonl", "args": {"data_path": "data/test.jsonl"}},
            "evaluators": [{"name": "relevance", "mapping": {"question": "dataset.question"}}],
            "connections": [{"name": "default", "api_key": "k", "endpoint": "http://localhost"}],
            "compute": {"type": "local"},
        }
    }
    path = tmp_path / "evals.yaml"
    path.write_text(yaml.dump(cfg, default_flow_style=False))
    return path


class TestValidateCommand:
    """Test ``ev validate``."""

    def test_validate_help(self, cli_runner: click.testing.CliRunner):
        result = cli_runner.invoke(cli, ["validate", "--help"])
        assert result.exit_code == 0
        assert "Validate configuration file" in result.output

    def test_validate_missing_config(self, cli_runner: click.testing.CliRunner, tmp_path):
        result = cli_runner.invoke(cli, ["validate", "--config", str(tmp_path / "nope.yaml")])
        assert result.exit_code != 0

    @patch("azure.ai.evaluation._engine.config.Config")
    @patch("azure.ai.evaluation._engine.cli.commands.validate.import_local_components")
    def test_validate_valid_config(self, mock_discover, mock_config_cls,
                                   cli_runner, valid_config_path):
        evaluator = MagicMock()
        evaluator.name = "relevance"
        mock_cfg = MagicMock()
        mock_cfg.experiment.name = "test-validate"
        mock_cfg.experiment.targets = [MagicMock()]
        mock_cfg.experiment.evaluators = [evaluator]
        mock_cfg.experiment.dataset = MagicMock()
        mock_cfg.experiment.dataset.name = "ds"
        mock_cfg.experiment.compute.type = "local"
        mock_cfg.experiment.output_path = "output"
        mock_cfg.deep_validate.return_value = []
        mock_config_cls.from_yaml.return_value = mock_cfg

        result = cli_runner.invoke(cli, ["validate", "--config", str(valid_config_path)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    @patch("azure.ai.evaluation._engine.config.Config")
    @patch("azure.ai.evaluation._engine.cli.commands.validate.import_local_components")
    def test_validate_invalid_config_parse_error(self, mock_discover, mock_config_cls,
                                                  cli_runner, tmp_path):
        bad_config = tmp_path / "bad.yaml"
        bad_config.write_text("not: valid: yaml: structure")
        mock_config_cls.from_yaml.side_effect = Exception("Invalid config structure")

        result = cli_runner.invoke(cli, ["validate", "--config", str(bad_config)])
        assert result.exit_code != 0

    @patch("azure.ai.evaluation._engine.config.Config")
    @patch("azure.ai.evaluation._engine.cli.commands.validate.import_local_components")
    def test_validate_json_output(self, mock_discover, mock_config_cls,
                                  cli_runner, valid_config_path):
        evaluator = MagicMock()
        evaluator.name = "relevance"
        mock_cfg = MagicMock()
        mock_cfg.experiment.name = "test-validate"
        mock_cfg.experiment.targets = [MagicMock()]
        mock_cfg.experiment.evaluators = [evaluator]
        mock_cfg.experiment.dataset = MagicMock()
        mock_cfg.experiment.dataset.name = "ds"
        mock_cfg.experiment.compute.type = "local"
        mock_cfg.experiment.output_path = "output"
        mock_cfg.deep_validate.return_value = []
        mock_config_cls.from_yaml.return_value = mock_cfg

        result = cli_runner.invoke(cli, ["validate", "--config", str(valid_config_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["valid"] is True
        assert isinstance(data["errors"], list)
        assert isinstance(data["warnings"], list)

    def test_validate_json_output_missing_config(self, cli_runner, tmp_path):
        result = cli_runner.invoke(cli, [
            "validate", "--config", str(tmp_path / "nope.yaml"), "--json",
        ])
        # JSON mode still outputs valid JSON even on errors
        data = json.loads(result.output.strip())
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    @patch("azure.ai.evaluation._engine.config.Config")
    @patch("azure.ai.evaluation._engine.cli.commands.validate.import_local_components")
    def test_validate_deep_validation_errors(self, mock_discover, mock_config_cls,
                                              cli_runner, valid_config_path):
        evaluator = MagicMock()
        evaluator.name = "relevance"
        mock_cfg = MagicMock()
        mock_cfg.experiment.name = "test-validate"
        mock_cfg.experiment.targets = [MagicMock()]
        mock_cfg.experiment.evaluators = [evaluator]
        mock_cfg.experiment.dataset = MagicMock()
        mock_cfg.experiment.dataset.name = "ds"
        mock_cfg.experiment.compute.type = "local"
        mock_cfg.experiment.output_path = "output"
        mock_cfg.deep_validate.return_value = ["Target 't1' not found in registry"]
        mock_config_cls.from_yaml.return_value = mock_cfg

        result = cli_runner.invoke(cli, ["validate", "--config", str(valid_config_path), "--json"])
        data = json.loads(result.output.strip())
        assert data["valid"] is False
        assert any("not found" in e for e in data["errors"])
