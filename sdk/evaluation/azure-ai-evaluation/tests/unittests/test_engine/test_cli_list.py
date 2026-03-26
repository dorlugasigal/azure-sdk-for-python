# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Tests for the ``discover`` CLI command."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import click.testing
import pytest

from azure.ai.evaluation._engine.cli import cli
from azure.ai.evaluation._engine.cli.utils.constants import BUILTIN_EVALUATORS

os.environ["AZURE_AI_EVAL_DISABLE_RICH"] = "true"


@pytest.fixture()
def cli_runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


class TestDiscoverCommand:
    """Test ``ev discover``."""

    def test_discover_help(self, cli_runner: click.testing.CliRunner):
        result = cli_runner.invoke(cli, ["discover", "--help"])
        assert result.exit_code == 0
        assert "Discover available components" in result.output

    @patch("azure.ai.evaluation._engine.cli.commands.list_cmd.import_local_components")
    @patch("azure.ai.evaluation._engine.cli.commands.list_cmd.discover_project_components")
    def test_discover_shows_sections(self, mock_discover, mock_import,
                                     cli_runner: click.testing.CliRunner):
        mock_discover.return_value = {"targets": ["my_target"], "evaluators": ["word_count"], "datasets": ["csv", "jsonl"]}
        result = cli_runner.invoke(cli, ["discover"])
        assert result.exit_code == 0
        assert "Project" in result.output
        assert "my_target" in result.output
        assert "word_count" in result.output
        assert "Built-in" in result.output

    @patch("azure.ai.evaluation._engine.cli.commands.list_cmd.import_local_components")
    @patch("azure.ai.evaluation._engine.cli.commands.list_cmd.discover_project_components")
    def test_discover_no_custom_components(self, mock_discover, mock_import,
                                           cli_runner: click.testing.CliRunner):
        mock_discover.return_value = {"targets": [], "evaluators": [], "datasets": []}
        result = cli_runner.invoke(cli, ["discover"])
        assert result.exit_code == 0
        assert "(none)" in result.output
        assert "Built-in" in result.output

    @patch("azure.ai.evaluation._engine.cli.commands.list_cmd.import_local_components")
    @patch("azure.ai.evaluation._engine.cli.commands.list_cmd.discover_project_components")
    def test_discover_json_output(self, mock_discover, mock_import,
                                  cli_runner: click.testing.CliRunner):
        mock_discover.return_value = {"targets": ["t1"], "evaluators": ["e1"], "datasets": ["csv"]}
        result = cli_runner.invoke(cli, ["discover", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["targets"] == [{"name": "t1"}]
        assert data["evaluators"]["custom"] == [{"name": "e1"}]
        assert len(data["evaluators"]["builtin"]) == len(BUILTIN_EVALUATORS)
        assert data["datasets"] == [{"name": "csv"}]
