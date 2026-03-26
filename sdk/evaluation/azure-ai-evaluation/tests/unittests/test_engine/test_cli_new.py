# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Tests for the ``new`` CLI command."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import click.testing
import pytest

from azure.ai.evaluation._engine.cli import cli

os.environ["AZURE_AI_EVAL_DISABLE_RICH"] = "true"


@pytest.fixture()
def cli_runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


class TestNewCommand:
    """Test project scaffolding via ``ev new``."""

    def test_new_help(self, cli_runner: click.testing.CliRunner):
        result = cli_runner.invoke(cli, ["new", "--help"])
        assert result.exit_code == 0
        assert "Create a new evaluation project" in result.output

    def test_new_creates_project(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "my_eval_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["new", project_name])
            assert result.exit_code == 0
            assert os.path.isdir(project_name)

    def test_new_creates_expected_files(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "test_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            cli_runner.invoke(cli, ["new", project_name])

            assert os.path.isfile(os.path.join(project_name, "pyproject.toml"))
            assert os.path.isfile(os.path.join(project_name, "config.yaml"))
            assert os.path.isdir(os.path.join(project_name, "data"))
            assert os.path.isfile(os.path.join(project_name, "data", "sample_dataset.jsonl"))
            assert os.path.isdir(os.path.join(project_name, "evaluators"))
            assert os.path.isfile(os.path.join(project_name, "evaluators", "word_count.py"))
            assert os.path.isdir(os.path.join(project_name, "targets"))
            assert os.path.isfile(os.path.join(project_name, "targets", "baseline.py"))
            assert os.path.isfile(os.path.join(project_name, ".gitignore"))
            assert os.path.isfile(os.path.join(project_name, ".env.sample"))
            assert os.path.isfile(os.path.join(project_name, "README.md"))

    def test_new_pyproject_has_project_name(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "named_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            cli_runner.invoke(cli, ["new", project_name])
            with open(os.path.join(project_name, "pyproject.toml")) as f:
                content = f.read()
            assert project_name in content

    def test_new_pyproject_has_correct_dependency(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "dep_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            cli_runner.invoke(cli, ["new", project_name])
            with open(os.path.join(project_name, "pyproject.toml")) as f:
                content = f.read()
            assert "azure-ai-evaluation" in content

    def test_new_config_has_evaluator_and_target_sections(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "config_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            cli_runner.invoke(cli, ["new", project_name])
            with open(os.path.join(project_name, "config.yaml")) as f:
                content = f.read()
            assert "evaluators:" in content
            assert "targets:" in content
            assert project_name in content

    def test_new_sample_data_is_valid_jsonl(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "jsonl_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            cli_runner.invoke(cli, ["new", project_name])
            data_path = os.path.join(project_name, "data", "sample_dataset.jsonl")
            with open(data_path) as f:
                lines = f.readlines()
            assert len(lines) == 3
            for line in lines:
                record = json.loads(line)
                assert "question" in record

    def test_new_duplicate_project_name(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "duplicate_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            cli_runner.invoke(cli, ["new", project_name])
            result = cli_runner.invoke(cli, ["new", project_name])
            assert result.exit_code != 0

    def test_new_force_overwrites(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "force_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            cli_runner.invoke(cli, ["new", project_name])
            result = cli_runner.invoke(cli, ["new", project_name, "--force"])
            assert result.exit_code == 0
            assert os.path.isdir(project_name)
            assert os.path.isfile(os.path.join(project_name, "pyproject.toml"))

    def test_new_evaluator_has_decorator(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "evaluator_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            cli_runner.invoke(cli, ["new", project_name])
            with open(os.path.join(project_name, "evaluators", "word_count.py")) as f:
                content = f.read()
            assert "@evaluator" in content
            assert "BaseEvaluator" in content
            assert "def compute" in content
            assert "def aggregate" in content

    def test_new_target_has_decorator(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "target_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            cli_runner.invoke(cli, ["new", project_name])
            with open(os.path.join(project_name, "targets", "baseline.py")) as f:
                content = f.read()
            assert "@target" in content
            assert "BaseTarget" in content
            assert "def infer" in content

    # --- Project name validation ---

    def test_new_valid_names(self, cli_runner: click.testing.CliRunner, tmp_path):
        for name in ["my-project", "my_project", "Project123", "a"]:
            with cli_runner.isolated_filesystem(temp_dir=tmp_path):
                result = cli_runner.invoke(cli, ["new", name])
                assert result.exit_code == 0, f"Expected success for name '{name}', got: {result.output}"

    def test_new_invalid_name_special_chars(self, cli_runner: click.testing.CliRunner, tmp_path):
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["new", "bad project!"])
            assert result.exit_code != 0

    def test_new_invalid_name_too_long(self, cli_runner: click.testing.CliRunner, tmp_path):
        long_name = "a" * 101
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["new", long_name])
            assert result.exit_code != 0

    # --- Output directory ---

    def test_new_output_directory(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "output_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            os.makedirs("custom_output")
            result = cli_runner.invoke(cli, ["new", project_name, "--output", "custom_output"])
            assert result.exit_code == 0
            assert os.path.isdir(os.path.join("custom_output", project_name))

    # --- Interactive mode ---

    def test_new_interactive_mode(self, cli_runner: click.testing.CliRunner, tmp_path):
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(
                cli,
                ["new", "interactive_project", "-i"],
                input="My custom description\n1\n1\n",
            )
            assert result.exit_code == 0
            assert os.path.isdir("interactive_project")
            with open(os.path.join("interactive_project", "pyproject.toml")) as f:
                content = f.read()
            assert "My custom description" in content

    # --- from-git ---

    def test_new_from_git(self, cli_runner: click.testing.CliRunner, tmp_path):
        project_name = "git_project"
        with cli_runner.isolated_filesystem(temp_dir=tmp_path):
            result = cli_runner.invoke(cli, ["new", project_name, "--from-git"])
            assert result.exit_code == 0
            with open(os.path.join(project_name, "pyproject.toml")) as f:
                content = f.read()
            assert "[tool.uv.sources]" in content
            assert "azure-sdk-for-python" in content
