# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Tests for the ``clear`` CLI command."""
from __future__ import annotations

import json
import os

import click.testing
import pytest

from azure.ai.evaluation._engine.cli import cli

os.environ["AZURE_AI_EVAL_DISABLE_RICH"] = "true"


@pytest.fixture()
def cli_runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


@pytest.fixture()
def experiment_dir(tmp_path):
    """Create mock experiment output folders with timestamps."""
    base = tmp_path / "output"
    for ts in ("20240101_120000", "20240202_130000", "20240303_140000"):
        run_dir = base / ts
        (run_dir / "logs").mkdir(parents=True)
        (run_dir / "results").mkdir(parents=True)
        (run_dir / "logs" / "run.log").write_text(f"Run at {ts}\n")
        (run_dir / "results" / "results.jsonl").write_text(
            json.dumps({"target": "t1", "status": "completed"}) + "\n"
        )
    return base


class TestClearCommand:
    """Test ``ev clear``."""

    def test_clear_help(self, cli_runner: click.testing.CliRunner):
        result = cli_runner.invoke(cli, ["clear", "--help"])
        assert result.exit_code == 0
        assert "Clear experiment output folders" in result.output
        assert "--force" in result.output
        assert "--keep-last" in result.output
        assert "--preview" in result.output

    def test_clear_no_experiments_dir(self, cli_runner: click.testing.CliRunner, tmp_path):
        result = cli_runner.invoke(cli, [
            "clear", "--path", str(tmp_path / "nonexistent"),
        ])
        assert result.exit_code != 0

    def test_clear_empty_dir(self, cli_runner: click.testing.CliRunner, tmp_path):
        empty = tmp_path / "empty_output"
        empty.mkdir()
        result = cli_runner.invoke(cli, ["clear", "--path", str(empty)])
        assert result.exit_code == 0
        assert "No output folders" in result.output

    def test_clear_preview(self, cli_runner: click.testing.CliRunner, experiment_dir):
        result = cli_runner.invoke(cli, [
            "clear", "--path", str(experiment_dir), "--preview",
        ])
        assert result.exit_code == 0
        assert "PREVIEW" in result.output
        assert "Would delete" in result.output
        # Nothing should be deleted
        assert len(list(experiment_dir.iterdir())) == 3

    def test_clear_force(self, cli_runner: click.testing.CliRunner, experiment_dir):
        result = cli_runner.invoke(cli, [
            "clear", "--path", str(experiment_dir), "--force",
        ])
        assert result.exit_code == 0
        assert "Removed" in result.output
        assert len(list(experiment_dir.iterdir())) == 0

    def test_clear_keep_last(self, cli_runner: click.testing.CliRunner, experiment_dir):
        result = cli_runner.invoke(cli, [
            "clear", "--path", str(experiment_dir), "--keep-last", "1", "--force",
        ])
        assert result.exit_code == 0
        remaining = list(experiment_dir.iterdir())
        assert len(remaining) == 1
        # The most recent folder should be kept
        assert remaining[0].name == "20240303_140000"

    def test_clear_keep_last_more_than_existing(self, cli_runner: click.testing.CliRunner, experiment_dir):
        result = cli_runner.invoke(cli, [
            "clear", "--path", str(experiment_dir), "--keep-last", "10",
        ])
        assert result.exit_code == 0
        assert "keeping all" in result.output.lower()
        assert len(list(experiment_dir.iterdir())) == 3

    def test_clear_logs_only(self, cli_runner: click.testing.CliRunner, experiment_dir):
        result = cli_runner.invoke(cli, [
            "clear", "--path", str(experiment_dir), "--logs-only", "--force",
        ])
        assert result.exit_code == 0
        # Experiment folders should still exist
        assert len(list(experiment_dir.iterdir())) == 3
        # But logs/ should be deleted
        for child in experiment_dir.iterdir():
            assert not (child / "logs").exists()
            assert (child / "results").exists()

    def test_clear_with_date_before(self, cli_runner: click.testing.CliRunner, experiment_dir):
        result = cli_runner.invoke(cli, [
            "clear", "--path", str(experiment_dir),
            "--before", "2024-02-01",
            "--force",
        ])
        assert result.exit_code == 0
        remaining = sorted(d.name for d in experiment_dir.iterdir())
        assert "20240101_120000" not in remaining
        assert "20240202_130000" in remaining
        assert "20240303_140000" in remaining
