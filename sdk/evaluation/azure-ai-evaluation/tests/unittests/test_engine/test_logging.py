# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for the logging module (setup_logger, get_console, LocalMetricsLogger)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from azure.ai.evaluation._engine.logging import (
    LocalMetricsLogger,
    get_console,
    setup_logger,
)
from azure.ai.evaluation._engine.logging.logger import (
    DEFAULT_LOGGER_NAME,
    LOG_FILE_NAME,
    _is_rich_compatible_environment,
    _use_rich,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset the root logger between tests."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


def _setup_clean_logger(
    name: str, logs_path: str, **kwargs: Any
) -> logging.Logger:
    """Create a fresh logger with cleared handlers."""
    lgr = logging.getLogger(name)
    lgr.handlers.clear()
    return setup_logger(logger_name=name, logs_path=logs_path, force=True, **kwargs)


# ---------------------------------------------------------------------------
# setup_logger
# ---------------------------------------------------------------------------

class TestSetupLogger:
    """Tests for setup_logger."""

    def test_creates_logger_with_handlers(self, tmp_path: Path) -> None:
        lgr = _setup_clean_logger("test_logger", str(tmp_path))
        assert lgr.name == "test_logger"
        assert len(lgr.handlers) == 2  # console + file

    def test_file_handler_creates_log_file(self, tmp_path: Path) -> None:
        _setup_clean_logger("test_file", str(tmp_path))
        assert (tmp_path / LOG_FILE_NAME).exists()

    def test_logger_writes_messages(self, tmp_path: Path) -> None:
        lgr = _setup_clean_logger("test_write", str(tmp_path))
        lgr.error("test error message")
        log_content = (tmp_path / LOG_FILE_NAME).read_text()
        assert "test error message" in log_content

    def test_logger_writes_warning(self, tmp_path: Path) -> None:
        lgr = _setup_clean_logger("test_warn", str(tmp_path))
        lgr.warning("a warning")
        log_content = (tmp_path / LOG_FILE_NAME).read_text()
        assert "a warning" in log_content

    def test_force_reconfigures(self, tmp_path: Path) -> None:
        lgr1 = _setup_clean_logger("test_force", str(tmp_path))
        n1 = len(lgr1.handlers)
        lgr2 = setup_logger(logger_name="test_force", logs_path=str(tmp_path), force=True)
        assert lgr1 is lgr2
        assert len(lgr2.handlers) == n1  # re-created, same count

    def test_no_duplicate_handlers_without_force(self, tmp_path: Path) -> None:
        lgr = _setup_clean_logger("test_nodup", str(tmp_path))
        n = len(lgr.handlers)
        lgr2 = setup_logger(logger_name="test_nodup", logs_path=str(tmp_path))
        assert len(lgr2.handlers) == n

    def test_respects_log_level_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        lgr = _setup_clean_logger("test_level", str(tmp_path))
        assert lgr.getEffectiveLevel() == logging.DEBUG

    def test_respects_log_path_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom_dir = tmp_path / "custom_logs"
        monkeypatch.setenv("LOG_PATH", str(custom_dir))
        _setup_clean_logger("test_path", str(tmp_path))
        assert (custom_dir / LOG_FILE_NAME).exists()


# ---------------------------------------------------------------------------
# Rich vs plain handler selection
# ---------------------------------------------------------------------------

class TestRichSelection:
    """Tests for Rich vs plain handler selection logic."""

    def test_rich_disabled_by_evee_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EVEE_DISABLE_RICH_LOGGING", "true")
        assert not _is_rich_compatible_environment()

    def test_rich_disabled_by_azure_ml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IS_AZURE_ML", "true")
        assert not _is_rich_compatible_environment()

    def test_rich_disabled_by_mcp_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EVEE_MCP_MODE", "true")
        assert not _is_rich_compatible_environment()

    def test_plain_handler_when_rich_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EVEE_DISABLE_RICH_LOGGING", "true")
        lgr = _setup_clean_logger("test_plain", str(tmp_path))
        handler_types = [type(h).__name__ for h in lgr.handlers]
        assert "StreamHandler" in handler_types
        assert "RichHandler" not in handler_types


# ---------------------------------------------------------------------------
# get_console
# ---------------------------------------------------------------------------

class TestGetConsole:
    """Tests for get_console."""

    def test_returns_none_when_rich_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EVEE_DISABLE_RICH_LOGGING", "true")
        # Reset shared console for clean test
        import azure.ai.evaluation._engine.logging.logger as mod
        original = mod._shared_console
        mod._shared_console = None
        try:
            assert get_console() is None
        finally:
            mod._shared_console = original


# ---------------------------------------------------------------------------
# LocalMetricsLogger
# ---------------------------------------------------------------------------

class TestLocalMetricsLogger:
    """Tests for LocalMetricsLogger."""

    def test_init_creates_output_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "metrics_output"
        logger = LocalMetricsLogger(str(out))
        assert out.exists()
        assert logger.output_dir == str(out)

    def test_log_results_writes_json(self, tmp_path: Path) -> None:
        out = tmp_path / "results"
        lgr = LocalMetricsLogger(str(out))

        mock_results = MagicMock()
        mock_results.to_dict.return_value = {
            "run_id": "test-run",
            "aggregated_metrics": {"accuracy": 0.85},
            "tags": {"model": "gpt"},
        }
        mock_results.run_id = "test-run"
        mock_results.tags = {"model": "gpt"}
        mock_results.aggregated_metrics = {"accuracy": 0.85}

        results_path = Path("experiment_results.jsonl")
        output = lgr.log_results(mock_results, results_path)

        assert output.exists()
        with open(output) as f:
            data = json.load(f)
        assert data["run_id"] == "test-run"
        assert data["aggregated_metrics"]["accuracy"] == 0.85

    def test_log_inference_result_appends_jsonl(self, tmp_path: Path) -> None:
        out = tmp_path / "inf_results"
        lgr = LocalMetricsLogger(str(out))

        mock_output = MagicMock()
        mock_output.to_dict.return_value = {"prediction": "yes", "score": 0.95}

        results_file = out / "results.jsonl"
        lgr.log_inference_result(mock_output, results_file)
        lgr.log_inference_result(mock_output, results_file)

        lines = results_file.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["score"] == 0.95

    def test_log_results_failure_raises(self, tmp_path: Path) -> None:
        out = tmp_path / "fail_results"
        lgr = LocalMetricsLogger(str(out))

        mock_results = MagicMock()
        mock_results.to_dict.side_effect = Exception("Serialization error")

        with pytest.raises(Exception, match="Serialization error"):
            lgr.log_results(mock_results, Path("res.jsonl"))

    def test_log_inference_result_failure_raises(self, tmp_path: Path) -> None:
        out = tmp_path / "fail_inf"
        lgr = LocalMetricsLogger(str(out))

        mock_output = MagicMock()
        mock_output.to_dict.side_effect = Exception("to_dict failed")

        with pytest.raises(Exception, match="to_dict failed"):
            lgr.log_inference_result(mock_output, out / "results.jsonl")
