# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Unit tests for component discovery (decorator_discovery → discovery).

Adapted from evee's test_decorator_discovery.py with import paths and
function names updated for the engine module.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azure.ai.evaluation._engine.discovery import (
    _DISCOVERED_DIRECTORIES,
    _IMPORTED_MODULES,
    _contains_decorator_syntax,
    _discover_in_directory,
    _has_decorator_on_class,
    discover_components,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TARGET_DECORATORS = {"model", "metric", "dataset", "target", "evaluator"}


@pytest.fixture()
def temp_project_dir(tmp_path):
    """Temporary project directory for discovery tests."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir


@pytest.fixture(autouse=True)
def clean_discovery_caches():
    """Snapshot and restore discovery caches between tests."""
    dirs_snap = _DISCOVERED_DIRECTORIES.copy()
    mods_snap = _IMPORTED_MODULES.copy()
    yield
    _DISCOVERED_DIRECTORIES.clear()
    _DISCOVERED_DIRECTORIES.update(dirs_snap)
    _IMPORTED_MODULES.clear()
    _IMPORTED_MODULES.update(mods_snap)


# ===========================================================================
# _contains_decorator_syntax  (fast text search)
# ===========================================================================


class TestContainsDecoratorSyntax:
    """Tests for the fast text-based decorator detection."""

    def test_detects_evaluator_decorator(self):
        content = "@evaluator(name='test')\nclass MyEval: pass"
        assert _contains_decorator_syntax(content, TARGET_DECORATORS) is True

    def test_detects_target_decorator(self):
        content = "@target(name='test')\nclass MyTarget: pass"
        assert _contains_decorator_syntax(content, TARGET_DECORATORS) is True

    def test_detects_dataset_decorator(self):
        content = "@dataset(name='test')\nclass MyDs: pass"
        assert _contains_decorator_syntax(content, TARGET_DECORATORS) is True

    def test_detects_legacy_model_decorator(self):
        content = "@model(name='test')\nclass MyModel: pass"
        assert _contains_decorator_syntax(content, TARGET_DECORATORS) is True

    def test_detects_legacy_metric_decorator(self):
        content = "@metric(name='test')\nclass MyMetric: pass"
        assert _contains_decorator_syntax(content, TARGET_DECORATORS) is True

    def test_returns_false_for_no_decorators(self):
        content = "def some_function():\n    return 42\n"
        assert _contains_decorator_syntax(content, TARGET_DECORATORS) is False


# ===========================================================================
# _has_decorator_on_class  (AST validation)
# ===========================================================================


class TestHasDecoratorOnClass:
    """Tests for AST-based decorator-on-class validation."""

    def test_decorator_call_on_class(self):
        """@evaluator(name='x') on a class is detected."""
        tree = ast.parse("@evaluator(name='test')\nclass MyEval:\n    pass")
        assert _has_decorator_on_class(tree, {"evaluator"}) is True

    def test_bare_decorator_on_class(self):
        """@target (no call parens) on a class is detected."""
        tree = ast.parse("@target\nclass MyTarget:\n    pass")
        assert _has_decorator_on_class(tree, {"target"}) is True

    def test_decorator_on_function_ignored(self):
        """Decorators on functions (not classes) are not detected."""
        tree = ast.parse("@evaluator(name='test')\ndef my_func():\n    pass")
        assert _has_decorator_on_class(tree, {"evaluator"}) is False

    def test_no_decorator(self):
        """File without decorators returns False."""
        tree = ast.parse("class Plain:\n    pass")
        assert _has_decorator_on_class(tree, TARGET_DECORATORS) is False


# ===========================================================================
# _discover_in_directory
# ===========================================================================


class TestDiscoverInDirectory:
    """Tests for recursive directory scanning."""

    def test_skips_excluded_directories(self, temp_project_dir, monkeypatch):
        """Files inside excluded dirs (.venv, __pycache__, etc.) are ignored."""
        monkeypatch.chdir(temp_project_dir)

        for dir_name in [".venv", "__pycache__", ".git", "node_modules", "output"]:
            d = temp_project_dir / dir_name
            d.mkdir()
            (d / "test.py").write_text(
                "@target(name='test')\nclass Test:\n    pass"
            )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            _discover_in_directory(temp_project_dir)

        mock_spec.assert_not_called()

    def test_skips_private_modules(self, temp_project_dir, monkeypatch):
        """Files starting with _ are skipped."""
        monkeypatch.chdir(temp_project_dir)
        (temp_project_dir / "__init__.py").write_text("# init")
        (temp_project_dir / "_private.py").write_text(
            "@target(name='test')\nclass Test:\n    pass"
        )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            _discover_in_directory(temp_project_dir)

        mock_spec.assert_not_called()

    def test_skips_files_without_decorators(self, temp_project_dir, monkeypatch):
        """Plain Python files are not imported."""
        monkeypatch.chdir(temp_project_dir)
        (temp_project_dir / "plain.py").write_text(
            "def some_function():\n    return 42\n"
        )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            _discover_in_directory(temp_project_dir)

        mock_spec.assert_not_called()

    def test_imports_file_with_target_decorator(self, temp_project_dir, monkeypatch):
        """File containing @target on a class triggers import."""
        monkeypatch.chdir(temp_project_dir)
        (temp_project_dir / "my_target.py").write_text(
            "@target(name='test_target')\nclass TestTarget:\n    pass\n"
        )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            mock_spec.return_value = None
            _discover_in_directory(temp_project_dir)

        mock_spec.assert_called_once()
        assert "my_target" in mock_spec.call_args[0][0]

    def test_imports_file_with_evaluator_decorator(
        self, temp_project_dir, monkeypatch
    ):
        """File containing @evaluator on a class triggers import."""
        monkeypatch.chdir(temp_project_dir)
        (temp_project_dir / "my_evaluator.py").write_text(
            "@evaluator(name='test_eval')\nclass TestEval:\n    pass\n"
        )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            mock_spec.return_value = None
            _discover_in_directory(temp_project_dir)

        mock_spec.assert_called_once()
        assert "my_evaluator" in mock_spec.call_args[0][0]

    def test_imports_file_with_dataset_decorator(
        self, temp_project_dir, monkeypatch
    ):
        """File containing @dataset on a class triggers import."""
        monkeypatch.chdir(temp_project_dir)
        (temp_project_dir / "my_dataset.py").write_text(
            "@dataset(name='test_ds')\nclass TestDs:\n    pass\n"
        )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            mock_spec.return_value = None
            _discover_in_directory(temp_project_dir)

        mock_spec.assert_called_once()
        assert "my_dataset" in mock_spec.call_args[0][0]

    def test_handles_import_errors_gracefully(self, temp_project_dir, monkeypatch):
        """Import failures are silently caught; discovery continues."""
        monkeypatch.chdir(temp_project_dir)
        (temp_project_dir / "broken.py").write_text(
            "@target(name='broken')\nclass Broken:\n    pass\n"
        )

        mock_spec = MagicMock()
        mock_spec.loader.exec_module.side_effect = ImportError("bad module")

        with (
            patch("importlib.util.spec_from_file_location", return_value=mock_spec),
            patch("importlib.util.module_from_spec", return_value=MagicMock()),
        ):
            # should not raise
            _discover_in_directory(temp_project_dir)

    def test_skips_decorators_on_functions(self, temp_project_dir, monkeypatch):
        """Decorators applied to functions (not classes) are ignored by AST."""
        monkeypatch.chdir(temp_project_dir)
        (temp_project_dir / "func_decorated.py").write_text(
            "@target(name='wrong')\ndef some_function():\n    pass\n"
        )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            _discover_in_directory(temp_project_dir)

        mock_spec.assert_not_called()

    def test_handles_directory_traversal_errors(
        self, temp_project_dir, monkeypatch
    ):
        """os.walk errors are caught; function does not raise."""
        monkeypatch.chdir(temp_project_dir)

        with patch("os.walk", side_effect=Exception("Traversal error")):
            _discover_in_directory(temp_project_dir)  # should not raise

    def test_correct_module_path_for_nested_files(
        self, temp_project_dir, monkeypatch
    ):
        """Nested files produce dot-separated module paths."""
        monkeypatch.chdir(temp_project_dir)
        subdir = temp_project_dir / "models" / "subdir"
        subdir.mkdir(parents=True)
        (subdir / "my_target.py").write_text(
            "@target(name='nested')\nclass NestedTarget:\n    pass\n"
        )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            mock_spec.return_value = None
            _discover_in_directory(temp_project_dir)

        mock_spec.assert_called_once()
        assert "models.subdir.my_target" in mock_spec.call_args[0][0]

    def test_multiple_decorators_in_one_file(self, temp_project_dir, monkeypatch):
        """File with multiple decorator types is imported once."""
        monkeypatch.chdir(temp_project_dir)
        (temp_project_dir / "multi.py").write_text(
            "@target(name='t')\nclass T:\n    pass\n\n"
            "@evaluator(name='e')\nclass E:\n    pass\n\n"
            "@dataset(name='d')\nclass D:\n    pass\n"
        )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            mock_spec.return_value = None
            _discover_in_directory(temp_project_dir)

        mock_spec.assert_called_once()

    def test_ignores_commented_decorators(self, temp_project_dir, monkeypatch):
        """Commented-out and docstring decorators are not imported."""
        monkeypatch.chdir(temp_project_dir)
        (temp_project_dir / "false_positive.py").write_text(
            '# @model(name="commented")\n'
            '# class CommentedModel: pass\n\n'
            '"""\n@model(name="docstring")\nclass DocModel: pass\n"""\n\n'
            "def regular_function():\n    pass\n"
        )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            _discover_in_directory(temp_project_dir)

        # AST phase rejects — no real class decorator found
        mock_spec.assert_not_called()

    def test_finds_real_decorator_despite_comments(
        self, temp_project_dir, monkeypatch
    ):
        """Real decorator is found even when comments also mention decorators."""
        monkeypatch.chdir(temp_project_dir)
        (temp_project_dir / "mixed.py").write_text(
            '# @model(name="fake")\n\n'
            '"""\n@metric(name="also_fake")\n"""\n\n'
            "@target(name='real')\nclass RealTarget:\n    pass\n"
        )

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            mock_spec.return_value = None
            _discover_in_directory(temp_project_dir)

        mock_spec.assert_called_once()

    def test_handles_nonexistent_directory(self):
        """Non-existent directory does not raise."""
        _discover_in_directory(Path("/non/existent/directory"))


# ===========================================================================
# discover_components
# ===========================================================================


class TestDiscoverComponents:
    """Tests for the top-level discover_components() function."""

    def test_caches_discovery(self, temp_project_dir, monkeypatch):
        """Repeated calls skip re-scanning the same directory."""
        monkeypatch.chdir(temp_project_dir)

        with patch(
            "azure.ai.evaluation._engine.discovery._discover_in_directory"
        ) as mock_discover:
            discover_components()
            discover_components()

            assert mock_discover.call_count == 1

    def test_force_rediscovery(self, temp_project_dir, monkeypatch):
        """force=True rescans even if directory was already scanned."""
        monkeypatch.chdir(temp_project_dir)

        with patch(
            "azure.ai.evaluation._engine.discovery._discover_in_directory"
        ) as mock_discover:
            discover_components()
            discover_components(force=True)

            assert mock_discover.call_count == 2
