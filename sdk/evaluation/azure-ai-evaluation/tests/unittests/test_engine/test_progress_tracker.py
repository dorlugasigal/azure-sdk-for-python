# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for ProgressTracker and _is_interactive_environment."""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from azure.ai.evaluation._engine.progress_tracker import (
    ProgressTracker,
    _is_interactive_environment,
)


# ---------------------------------------------------------------------------
# _is_interactive_environment
# ---------------------------------------------------------------------------


class TestIsInteractiveEnvironment:
    """Tests for the environment-detection helper."""

    def test_returns_true_by_default(self) -> None:
        env = {
            "AZURE_AI_EVAL_DISABLE_RICH": "false",
            "IS_AZURE_ML": "false",
            "CI": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            assert _is_interactive_environment() is True

    def test_disable_rich_env_var(self) -> None:
        with patch.dict(os.environ, {"AZURE_AI_EVAL_DISABLE_RICH": "true"}, clear=True):
            assert _is_interactive_environment() is False

    def test_azure_ml_env(self) -> None:
        with patch.dict(os.environ, {"IS_AZURE_ML": "true"}, clear=True):
            assert _is_interactive_environment() is False

    def test_ci_env(self) -> None:
        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            assert _is_interactive_environment() is False

    def test_case_insensitive(self) -> None:
        with patch.dict(os.environ, {"IS_AZURE_ML": "True"}, clear=True):
            assert _is_interactive_environment() is False


# ---------------------------------------------------------------------------
# ProgressTracker — non-interactive mode
# ---------------------------------------------------------------------------


class TestProgressTrackerNonInteractive:
    """Tests for ProgressTracker in non-interactive (logging) mode."""

    @pytest.fixture(autouse=True)
    def _force_non_interactive(self) -> None:
        """Ensure all tests in this class run in non-interactive mode."""
        os.environ["AZURE_AI_EVAL_DISABLE_RICH"] = "true"
        yield  # type: ignore[misc]
        os.environ["AZURE_AI_EVAL_DISABLE_RICH"] = "true"  # restore

    def test_init(self) -> None:
        tracker = ProgressTracker(total_targets=3)

        assert tracker._total_targets == 3
        assert tracker._is_interactive is False
        assert tracker._completed_targets == 0
        assert tracker._completed_records == 0

    def test_context_manager_logs_mode(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            with ProgressTracker(total_targets=1):
                pass

        assert "non-interactive" in caplog.text

    def test_begin_target_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            with ProgressTracker(total_targets=2) as tracker:
                tracker.begin_target("gpt-4o", total_records=100)

        assert "gpt-4o" in caplog.text
        assert "100 records" in caplog.text

    def test_advance_logs_at_intervals(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            with ProgressTracker(total_targets=1, log_interval_pct=50) as tracker:
                tracker.begin_target("model-a", total_records=10)
                for _ in range(10):
                    tracker.advance()

        # 50% interval on 10 records → log at record 5 and 10
        assert "50.0%" in caplog.text
        assert "100.0%" in caplog.text

    def test_advance_logs_completion(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            with ProgressTracker(total_targets=1) as tracker:
                tracker.begin_target("model-a", total_records=5)
                for _ in range(5):
                    tracker.advance()

        assert "100.0%" in caplog.text

    def test_advance_small_dataset(self, caplog: pytest.LogCaptureFixture) -> None:
        """Datasets smaller than the interval log every record."""
        with caplog.at_level(logging.INFO):
            with ProgressTracker(total_targets=1) as tracker:
                tracker.begin_target("model-a", total_records=3)
                for _ in range(3):
                    tracker.advance()

        # interval = max(1, 3*10//100) = max(1,0) = 1 → every record logged
        assert "1/3" in caplog.text
        assert "2/3" in caplog.text
        assert "3/3" in caplog.text

    def test_finish_target(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            with ProgressTracker(total_targets=2) as tracker:
                tracker.begin_target("model-a", total_records=1)
                tracker.advance()
                tracker.finish_target()

        assert "Completed model-a" in caplog.text
        assert "1/2 targets" in caplog.text

    def test_begin_target_resets_completed_records(self) -> None:
        with ProgressTracker(total_targets=2) as tracker:
            tracker.begin_target("m1", total_records=5)
            for _ in range(5):
                tracker.advance()
            assert tracker._completed_records == 5

            tracker.finish_target()
            tracker.begin_target("m2", total_records=3)
            assert tracker._completed_records == 0

    def test_full_workflow(self) -> None:
        with ProgressTracker(total_targets=2) as tracker:
            tracker.begin_target("m1", total_records=3)
            for _ in range(3):
                tracker.advance()
            tracker.finish_target()

            tracker.begin_target("m2", total_records=2)
            for _ in range(2):
                tracker.advance()
            tracker.finish_target()

        assert tracker._completed_targets == 2

    def test_exit_without_rich(self) -> None:
        """__exit__ is safe even when no Rich progress was created."""
        with ProgressTracker(total_targets=1) as tracker:
            assert tracker._progress is None

        # No exception raised


# ---------------------------------------------------------------------------
# ProgressTracker — interactive mode
# ---------------------------------------------------------------------------


class TestProgressTrackerInteractive:
    """Tests for ProgressTracker in interactive (Rich) mode."""

    def test_init_interactive(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "azure.ai.evaluation._engine.progress_tracker._is_interactive_environment",
                return_value=True,
            ):
                tracker = ProgressTracker(total_targets=2)
                assert tracker._is_interactive is True

    def test_context_manager_creates_rich_progress(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "azure.ai.evaluation._engine.progress_tracker._is_interactive_environment",
                return_value=True,
            ):
                tracker = ProgressTracker(total_targets=2)

                with tracker:
                    # Rich Progress object should be created
                    assert tracker._progress is not None
                    assert tracker._targets_task is not None

    def test_begin_target_creates_task(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "azure.ai.evaluation._engine.progress_tracker._is_interactive_environment",
                return_value=True,
            ):
                tracker = ProgressTracker(total_targets=1)

                with tracker:
                    tracker.begin_target("gpt-4o", total_records=50)
                    assert tracker._current_task is not None

    def test_rich_import_failure_falls_back(self, caplog: pytest.LogCaptureFixture) -> None:
        """When Rich is not installed, fall back to logging mode."""
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "azure.ai.evaluation._engine.progress_tracker._is_interactive_environment",
                return_value=True,
            ):
                tracker = ProgressTracker(total_targets=1)
                # Simulate Rich import failure
                with patch("builtins.__import__", side_effect=ImportError("no rich")):
                    with caplog.at_level(logging.INFO):
                        with tracker:
                            pass
                assert tracker._is_interactive is False
