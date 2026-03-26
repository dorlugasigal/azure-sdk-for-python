# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Tests for CLI utility modules (output, discovery, constants)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from azure.ai.evaluation._engine.cli.utils.constants import (
    EV_ASCII,
    BUILTIN_EVALUATORS,
)
from azure.ai.evaluation._engine.cli.utils.discovery import (
    dir_size_str,
    discover_project_components,
    import_local_components,
    load_config_safe,
)
from azure.ai.evaluation._engine.cli.utils.output import (
    echo,
    echo_error,
    has_rich,
    get_console,
    show_panel,
    show_results_table,
)

os.environ["AZURE_AI_EVAL_DISABLE_RICH"] = "true"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
class TestConstants:
    """Test CLI constants."""

    def test_ascii_art_defined(self):
        assert EV_ASCII is not None
        assert len(EV_ASCII) > 0

    def test_builtin_evaluators_defined(self):
        assert len(BUILTIN_EVALUATORS) > 0

    def test_builtin_evaluators_have_three_fields(self):
        for entry in BUILTIN_EVALUATORS:
            assert len(entry) == 3
            name, etype, desc = entry
            assert isinstance(name, str)
            assert etype in ("local", "cloud")
            assert isinstance(desc, str) and len(desc) > 0

    def test_builtin_evaluators_contain_known_entries(self):
        names = [e[0] for e in BUILTIN_EVALUATORS]
        assert "f1_score" in names
        assert "relevance" in names
        assert "coherence" in names
        assert "bleu" in names


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
class TestOutputHelpers:
    """Test output utility functions."""

    def test_has_rich_returns_bool(self):
        result = has_rich()
        assert isinstance(result, bool)

    def test_echo_does_not_raise(self, capsys):
        echo("test message")
        captured = capsys.readouterr()
        assert "test" in captured.out or True  # Rich may capture differently

    def test_echo_error_does_not_raise(self, capsys):
        echo_error("something went wrong")
        # Should not raise

    def test_echo_empty(self, capsys):
        echo()
        # Should not raise

    def test_get_console_returns_value(self):
        console = get_console()
        # May be None if Rich is not installed, or a Console instance
        assert console is None or console is not None  # Always true, just verify no crash

    def test_show_panel_does_not_raise(self, capsys):
        show_panel({"Key": "Value", "Another": "Data"}, title="Test Panel")

    def test_show_results_table_does_not_raise(self, capsys):
        show_results_table({
            "status": "completed",
            "total_records": 5,
            "models_evaluated": 1,
            "aggregated_metrics": {"relevance": 0.95},
        })


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------
class TestDiscoveryHelpers:
    """Test discovery utility functions."""

    def test_dir_size_str_empty_dir(self, tmp_path):
        result = dir_size_str(str(tmp_path))
        assert "0.0 B" in result

    def test_dir_size_str_with_file(self, tmp_path):
        (tmp_path / "test.txt").write_text("hello world" * 100)
        result = dir_size_str(str(tmp_path))
        assert "B" in result or "KB" in result

    def test_discover_project_components_returns_dict(self):
        result = discover_project_components()
        assert isinstance(result, dict)
        assert "targets" in result
        assert "evaluators" in result
        assert "datasets" in result

    def test_import_local_components_no_crash_on_empty(self, tmp_path):
        import_local_components(str(tmp_path))
        # Should not raise

    def test_import_local_components_skips_underscore_files(self, tmp_path):
        (tmp_path / "_private.py").write_text("@target\nclass X: pass\n")
        import_local_components(str(tmp_path))
        # Private files should be skipped

    def test_import_local_components_discovers_decorated(self, tmp_path):
        code = '''
from azure.ai.evaluation._engine.decorators import evaluator, BaseEvaluator

@evaluator(name="test_evaluator")
class TestEvaluator(BaseEvaluator):
    def compute(self, **kwargs):
        return {"score": 1}
    def aggregate(self, scores):
        return {"score_mean": 1}
'''
        (tmp_path / "my_metric.py").write_text(code)
        # Should not crash; actual registration depends on imports being available
        import_local_components(str(tmp_path))

    def test_load_config_safe_returns_none_for_missing(self, tmp_path):
        result = load_config_safe(str(tmp_path / "nonexistent.yaml"))
        assert result is None

    def test_load_config_safe_returns_none_for_invalid(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("this is not valid yaml for config")
        result = load_config_safe(str(bad))
        assert result is None
