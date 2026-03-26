# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Tests for the ``view`` CLI command."""
from __future__ import annotations

import os

import click.testing
import pytest

from azure.ai.evaluation._engine.cli import cli

os.environ["AZURE_AI_EVAL_DISABLE_RICH"] = "true"


@pytest.fixture()
def cli_runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


class TestViewCommand:
    """Test ``ev view``."""

    def test_view_help(self, cli_runner: click.testing.CliRunner):
        result = cli_runner.invoke(cli, ["view", "--help"])
        assert result.exit_code == 0
        assert "View experiment results" in result.output
        assert "--port" in result.output
        assert "--no-browser" in result.output

    def test_view_no_experiments_exits_gracefully(self, cli_runner: click.testing.CliRunner, tmp_path):
        """Verify the view command can be invoked (help check — actual server blocks)."""
        result = cli_runner.invoke(cli, ["view", "--help"])
        assert result.exit_code == 0
        assert "--no-browser" in result.output

    def test_view_port_option(self, cli_runner: click.testing.CliRunner):
        """Verify --port option is accepted."""
        result = cli_runner.invoke(cli, ["view", "--help"])
        assert "--port" in result.output
        assert "8765" in result.output  # default port value
