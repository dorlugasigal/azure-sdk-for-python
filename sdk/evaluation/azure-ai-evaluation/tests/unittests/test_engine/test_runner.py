# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for ExperimentRunner."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from azure.ai.evaluation._engine.runner import ExperimentRunner

_MOD = "azure.ai.evaluation._engine.runner"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> ExperimentRunner:
    return ExperimentRunner()


@pytest.fixture()
def mock_config() -> MagicMock:
    """Mock Config object returned by Config.from_yaml."""
    cfg = MagicMock()
    cfg.experiment.compute = MagicMock()
    cfg.experiment.compute.azure_ai_project = None
    cfg.experiment.connections = []
    return cfg


# ---------------------------------------------------------------------------
# _select_backend
# ---------------------------------------------------------------------------


class TestSelectBackend:
    def test_local_by_default(self, runner: ExperimentRunner, mock_config: MagicMock) -> None:
        from azure.ai.evaluation._engine.compute import LocalComputeBackend

        backend = runner._select_backend(mock_config, remote_compute=False)
        assert isinstance(backend, LocalComputeBackend)

    def test_remote_with_compute_endpoint(
        self, runner: ExperimentRunner, mock_config: MagicMock
    ) -> None:
        from azure.ai.evaluation._engine.compute import FoundryComputeBackend

        mock_config.experiment.compute.azure_ai_project = "https://my-project.azure.com"
        backend = runner._select_backend(mock_config, remote_compute=True)
        assert isinstance(backend, FoundryComputeBackend)

    def test_remote_with_connection_endpoint(
        self, runner: ExperimentRunner, mock_config: MagicMock
    ) -> None:
        from azure.ai.evaluation._engine.compute import FoundryComputeBackend

        mock_config.experiment.compute.azure_ai_project = None
        conn = MagicMock()
        conn.azure_ai_project = "https://conn-project.azure.com"
        mock_config.experiment.connections = [conn]

        backend = runner._select_backend(mock_config, remote_compute=True)
        assert isinstance(backend, FoundryComputeBackend)

    def test_remote_no_endpoint_raises(
        self, runner: ExperimentRunner, mock_config: MagicMock
    ) -> None:
        mock_config.experiment.compute.azure_ai_project = None
        mock_config.experiment.connections = []

        with pytest.raises(ValueError, match="Remote compute requested"):
            runner._select_backend(mock_config, remote_compute=True)

    def test_remote_no_compute_config(
        self, runner: ExperimentRunner, mock_config: MagicMock
    ) -> None:
        mock_config.experiment.compute = None
        mock_config.experiment.connections = []

        with pytest.raises(ValueError, match="Remote compute requested"):
            runner._select_backend(mock_config, remote_compute=True)


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


class TestRun:
    def test_run_local_default(self, runner: ExperimentRunner) -> None:
        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch.object(runner, "_select_backend") as mock_select,
        ):
            mock_cfg = MagicMock()
            MockConfig.from_yaml.return_value = mock_cfg

            mock_backend = MagicMock()
            mock_job = MagicMock()
            mock_backend.submit.return_value = mock_job
            mock_select.return_value = mock_backend

            result = runner.run(config_path="config.yaml")

            MockConfig.from_yaml.assert_called_once_with("config.yaml")
            mock_backend.submit.assert_called_once()
            assert result is mock_job

    def test_run_loads_env_file(self, runner: ExperimentRunner, tmp_path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\n")

        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch.object(runner, "_select_backend") as mock_select,
            patch(f"{_MOD}.load_dotenv", create=True) as mock_dotenv,
        ):
            mock_cfg = MagicMock()
            MockConfig.from_yaml.return_value = mock_cfg
            mock_select.return_value = MagicMock()

            # Patch the import to succeed
            with patch.dict("sys.modules", {"dotenv": MagicMock(load_dotenv=mock_dotenv)}):
                runner.run(config_path="config.yaml", env_path=str(env_file))

    def test_run_with_remote_compute(self, runner: ExperimentRunner) -> None:
        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch.object(runner, "_select_backend") as mock_select,
        ):
            mock_cfg = MagicMock()
            MockConfig.from_yaml.return_value = mock_cfg
            mock_select.return_value = MagicMock()

            runner.run(config_path="config.yaml", remote_compute=True)

            mock_select.assert_called_once_with(mock_cfg, True)

    def test_run_passes_context_fields(self, runner: ExperimentRunner) -> None:
        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch.object(runner, "_select_backend") as mock_select,
        ):
            MockConfig.from_yaml.return_value = MagicMock()
            mock_backend = MagicMock()
            mock_select.return_value = mock_backend

            runner.run(
                config_path="cfg.yaml",
                env_path=".env",
                dataset_path="data.jsonl",
                model_filter=["gpt-4"],
            )

            call_args = mock_backend.submit.call_args
            context = call_args[0][0]  # first positional arg

            assert context.config_path == "cfg.yaml"
            assert context.env_path == ".env"
            assert context.dataset_path == "data.jsonl"
            assert context.model_filter == ["gpt-4"]
