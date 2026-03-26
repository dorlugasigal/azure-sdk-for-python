# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Tests for CLI main entry point and environment delegation."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import click.testing
import pytest

from azure.ai.evaluation._engine.cli import (
    cli,
    main,
    _should_delegate_to_project_env,
    _extract_project_info_from_args,
    _normalize_cli_args_for_delegation,
    _NON_DELEGATED_COMMANDS,
    OrderedGroup,
)

os.environ["AZURE_AI_EVAL_DISABLE_RICH"] = "true"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def cli_runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


# ---------------------------------------------------------------------------
# CLI group basics
# ---------------------------------------------------------------------------
class TestCLI:
    """Test the main Click group."""

    def test_help_flag(self, cli_runner: click.testing.CliRunner):
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Azure AI Evaluation" in result.output

    def test_version_flag(self, cli_runner: click.testing.CliRunner):
        result = cli_runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "2.0.0a1" in result.output

    def test_unknown_command(self, cli_runner: click.testing.CliRunner):
        result = cli_runner.invoke(cli, ["nonexistent"])
        assert result.exit_code != 0

    def test_no_args_shows_help(self, cli_runner: click.testing.CliRunner):
        result = cli_runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "Azure AI Evaluation" in result.output

    @pytest.mark.parametrize(
        "name",
        ["run", "new", "validate", "discover", "view", "clear", "compute", "target", "evaluator", "dataset"],
    )
    def test_command_registered(self, name: str):
        assert name in cli.commands

    def test_ordered_group_preserves_order(self):
        assert isinstance(cli, OrderedGroup)
        names = list(cli.commands.keys())
        assert names.index("run") < names.index("new")
        assert names.index("validate") < names.index("discover")


# ---------------------------------------------------------------------------
# Delegation logic
# ---------------------------------------------------------------------------
class TestDelegationLogic:
    """Test _should_delegate_to_project_env helper."""

    def test_no_args_returns_false(self):
        with patch.object(sys, "argv", ["ev"]):
            assert _should_delegate_to_project_env() is False

    def test_help_flag_returns_false(self):
        with patch.object(sys, "argv", ["ev", "--help"]):
            assert _should_delegate_to_project_env() is False

    def test_version_flag_returns_false(self):
        with patch.object(sys, "argv", ["ev", "--version"]):
            assert _should_delegate_to_project_env() is False

    @pytest.mark.parametrize("cmd", list(_NON_DELEGATED_COMMANDS))
    def test_non_delegated_commands(self, cmd: str):
        with patch.object(sys, "argv", ["ev", cmd]):
            assert _should_delegate_to_project_env() is False

    def test_delegated_command_returns_true(self):
        with patch.object(sys, "argv", ["ev", "run"]):
            assert _should_delegate_to_project_env() is True

    def test_validate_is_delegated(self):
        with patch.object(sys, "argv", ["ev", "validate"]):
            assert _should_delegate_to_project_env() is True

    def test_only_flags_returns_false(self):
        with patch.object(sys, "argv", ["ev", "--plain"]):
            assert _should_delegate_to_project_env() is False


# ---------------------------------------------------------------------------
# Path normalisation
# ---------------------------------------------------------------------------
class TestNormalizeCLIArgs:
    """Test _normalize_cli_args_for_delegation."""

    def test_absolute_paths_unchanged(self):
        args = ["run", "--config", "/abs/path/config.yaml"]
        result = _normalize_cli_args_for_delegation(args)
        assert result[2] == "/abs/path/config.yaml"

    def test_relative_path_made_absolute(self):
        args = ["run", "--config", "evals.yaml"]
        result = _normalize_cli_args_for_delegation(args)
        assert os.path.isabs(result[2])

    def test_path_flag_normalised(self):
        args = ["run", "--path", "my_project"]
        result = _normalize_cli_args_for_delegation(args)
        assert os.path.isabs(result[2])

    def test_relative_with_dot_slash(self):
        args = ["run", "--config", "./evals.yaml"]
        result = _normalize_cli_args_for_delegation(args)
        assert os.path.isabs(result[2])

    def test_non_path_args_unchanged(self):
        args = ["run", "--models", "target_a,target_b"]
        result = _normalize_cli_args_for_delegation(args)
        assert result == args


# ---------------------------------------------------------------------------
# Extract project info
# ---------------------------------------------------------------------------
class TestExtractProjectInfo:
    """Test _extract_project_info_from_args."""

    def test_defaults(self):
        with patch.object(sys, "argv", ["ev", "run"]):
            project_path, config_path, config_explicit, env_path = (
                _extract_project_info_from_args()
            )
            assert project_path == os.getcwd()
            assert config_explicit is False

    def test_explicit_config(self, tmp_path):
        cfg = tmp_path / "custom.yaml"
        cfg.write_text("experiment: {}")
        with patch.object(sys, "argv", ["ev", "run", "--config", str(cfg)]):
            _, config_path, config_explicit, _ = _extract_project_info_from_args()
            assert config_explicit is True
            assert config_path == str(cfg)

    def test_explicit_path(self, tmp_path):
        with patch.object(sys, "argv", ["ev", "run", "-p", str(tmp_path)]):
            project_path, _, _, _ = _extract_project_info_from_args()
            assert project_path == str(tmp_path)

    def test_nonexistent_path_exits(self, tmp_path):
        bad = str(tmp_path / "does_not_exist")
        with patch.object(sys, "argv", ["ev", "run", "-p", bad]):
            with pytest.raises(SystemExit):
                _extract_project_info_from_args()


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------
class TestMainFunction:
    """Test main() entry point dispatch."""

    def test_direct_mode_invokes_cli(self):
        env = os.environ.copy()
        env["EV_EXECUTION_MODE"] = "direct"
        with patch.dict(os.environ, env), \
             patch("azure.ai.evaluation._engine.cli.cli") as mock_cli:
            mock_cli.return_value = None
            with patch.object(sys, "argv", ["ev", "--help"]):
                main()
            mock_cli.assert_called_once()

    def test_plain_flag_sets_env(self):
        with patch.dict(os.environ, {"EV_EXECUTION_MODE": "direct"}, clear=False), \
             patch.object(sys, "argv", ["ev", "--plain", "--help"]), \
             patch("azure.ai.evaluation._engine.cli.cli"):
            main()
            assert os.environ.get("EV_DISABLE_RICH_LOGGING") == "true"

    @patch("azure.ai.evaluation._engine.cli.cli")
    @patch("azure.ai.evaluation._engine.cli._execute_in_project_env")
    @patch("azure.ai.evaluation._engine.cli._should_delegate_to_project_env", return_value=True)
    def test_delegation_called(self, mock_should, mock_exec, mock_cli):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EV_EXECUTION_MODE", None)
            mock_cli.return_value = None
            with patch.object(sys, "argv", ["ev", "run"]):
                main()
            mock_exec.assert_called_once()

    @patch("azure.ai.evaluation._engine.cli._should_delegate_to_project_env", return_value=False)
    def test_non_delegated_invokes_cli(self, mock_should):
        with patch.dict(os.environ, {}, clear=False), \
             patch("azure.ai.evaluation._engine.cli.cli") as mock_cli:
            os.environ.pop("EV_EXECUTION_MODE", None)
            mock_cli.return_value = None
            with patch.object(sys, "argv", ["ev", "new"]):
                main()
            mock_cli.assert_called_once()
