# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Tests for the run CLI command."""
from __future__ import annotations

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
def valid_config(tmp_path):
    """Create a minimal valid config file in tmp_path."""
    cfg = {
        "experiment": {
            "name": "test-run",
            "targets": [{"name": "t1", "type": "custom", "args": {"temperature": [0.7]}}],
            "dataset": {"name": "ds", "type": "jsonl", "args": {"data_path": "data/test.jsonl"}},
            "evaluators": [{"name": "relevance", "mapping": {"question": "dataset.question"}}],
            "connections": [{"name": "default", "api_key": "k", "endpoint": "http://localhost"}],
            "compute": {"type": "local"},
        }
    }
    config_path = tmp_path / "evals.yaml"
    config_path.write_text(yaml.dump(cfg, default_flow_style=False))
    return config_path


class TestRunCommand:
    """Tests for the ``run`` command."""

    def test_run_help(self, cli_runner: click.testing.CliRunner):
        result = cli_runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "Run evaluation" in result.output
        assert "--remote" in result.output
        assert "--models" in result.output

    def test_run_missing_config(self, cli_runner: click.testing.CliRunner, tmp_path):
        result = cli_runner.invoke(cli, ["run", "--path", str(tmp_path), "--config", "nonexistent.yaml"])
        assert result.exit_code != 0

    @patch("azure.ai.evaluation._engine.runner.ExperimentRunner")
    @patch("azure.ai.evaluation._engine.compute.JobStatus")
    @patch("azure.ai.evaluation._engine.cli.commands.run.load_config_safe")
    @patch("azure.ai.evaluation._engine.cli.commands.run.import_local_components")
    def test_run_valid_config(self, mock_discover, mock_load_cfg, mock_status_cls, mock_runner_cls,
                              cli_runner, valid_config):
        evaluator = MagicMock()
        evaluator.name = "relevance"
        mock_cfg = MagicMock()
        mock_cfg.experiment.name = "test-run"
        mock_cfg.experiment.evaluators = [evaluator]
        mock_cfg.experiment.dataset.name = "ds"
        mock_load_cfg.return_value = mock_cfg

        mock_job = MagicMock()
        mock_job.status = mock_status_cls.COMPLETED
        mock_job.metadata = {
            "status": "completed",
            "total_records": 3,
            "models_evaluated": 1,
            "execution_type": "local",
            "aggregated_metrics": {},
        }
        mock_runner_cls.return_value.run.return_value = mock_job

        result = cli_runner.invoke(cli, [
            "run",
            "--path", str(valid_config.parent),
            "--config", valid_config.name,
            "-y",
        ])
        assert result.exit_code == 0
        mock_runner_cls.return_value.run.assert_called_once()

    @patch("azure.ai.evaluation._engine.runner.ExperimentRunner")
    @patch("azure.ai.evaluation._engine.compute.JobStatus")
    @patch("azure.ai.evaluation._engine.cli.commands.run.load_config_safe")
    @patch("azure.ai.evaluation._engine.cli.commands.run.import_local_components")
    def test_run_remote_flag(self, mock_discover, mock_load_cfg, mock_status_cls, mock_runner_cls,
                             cli_runner, valid_config):
        evaluator = MagicMock()
        evaluator.name = "relevance"
        mock_cfg = MagicMock()
        mock_cfg.experiment.name = "test-run"
        mock_cfg.experiment.evaluators = [evaluator]
        mock_cfg.experiment.dataset.name = "ds"
        mock_load_cfg.return_value = mock_cfg

        mock_job = MagicMock()
        mock_job.status = mock_status_cls.COMPLETED
        mock_job.metadata = {"execution_type": "remote", "status": "completed",
                             "total_records": 3, "models_evaluated": 1}
        mock_job.job_id = "job-123"
        mock_runner_cls.return_value.run.return_value = mock_job

        result = cli_runner.invoke(cli, [
            "run", "--path", str(valid_config.parent),
            "--config", valid_config.name,
            "--remote", "-y",
        ])
        assert result.exit_code == 0
        call_kwargs = mock_runner_cls.return_value.run.call_args
        assert call_kwargs[1]["remote_compute"] is True

    @patch("azure.ai.evaluation._engine.runner.ExperimentRunner")
    @patch("azure.ai.evaluation._engine.compute.JobStatus")
    @patch("azure.ai.evaluation._engine.cli.commands.run.load_config_safe")
    @patch("azure.ai.evaluation._engine.cli.commands.run.import_local_components")
    def test_run_models_filter(self, mock_discover, mock_load_cfg, mock_status_cls, mock_runner_cls,
                               cli_runner, valid_config):
        evaluator = MagicMock()
        evaluator.name = "relevance"
        mock_cfg = MagicMock()
        mock_cfg.experiment.name = "test-run"
        mock_cfg.experiment.evaluators = [evaluator]
        mock_cfg.experiment.dataset.name = "ds"
        mock_load_cfg.return_value = mock_cfg

        mock_job = MagicMock()
        mock_job.status = mock_status_cls.COMPLETED
        mock_job.metadata = {"execution_type": "local", "status": "completed",
                             "total_records": 1, "models_evaluated": 1,
                             "aggregated_metrics": {}}
        mock_runner_cls.return_value.run.return_value = mock_job

        result = cli_runner.invoke(cli, [
            "run", "--path", str(valid_config.parent),
            "--config", valid_config.name,
            "--models", "target_a,target_b", "-y",
        ])
        assert result.exit_code == 0
        call_kwargs = mock_runner_cls.return_value.run.call_args
        assert call_kwargs[1]["model_filter"] == ["target_a", "target_b"]

    @patch("azure.ai.evaluation._engine.runner.ExperimentRunner")
    @patch("azure.ai.evaluation._engine.compute.JobStatus")
    @patch("azure.ai.evaluation._engine.cli.commands.run.load_config_safe")
    @patch("azure.ai.evaluation._engine.cli.commands.run.import_local_components")
    def test_run_failed_job(self, mock_discover, mock_load_cfg, mock_status_cls, mock_runner_cls,
                            cli_runner, valid_config):
        evaluator = MagicMock()
        evaluator.name = "relevance"
        mock_cfg = MagicMock()
        mock_cfg.experiment.name = "test-run"
        mock_cfg.experiment.evaluators = [evaluator]
        mock_cfg.experiment.dataset.name = "ds"
        mock_load_cfg.return_value = mock_cfg

        mock_job = MagicMock()
        mock_job.status = mock_status_cls.FAILED
        mock_job.metadata = {"error": "Something went wrong"}
        mock_runner_cls.return_value.run.return_value = mock_job

        result = cli_runner.invoke(cli, [
            "run", "--path", str(valid_config.parent),
            "--config", valid_config.name, "-y",
        ])
        assert result.exit_code != 0
