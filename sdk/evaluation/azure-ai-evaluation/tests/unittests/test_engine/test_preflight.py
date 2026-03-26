# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for pre-flight checks."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from azure.ai.evaluation._engine.preflight import (
    CheckResult,
    CheckStatus,
    COMBINATION_COUNT_WARNING_THRESHOLD,
    _check_local_path_dependencies,
    _count_target_combinations,
    run_preflight_checks,
)

_MOD = "azure.ai.evaluation._engine.preflight"


# ---------------------------------------------------------------------------
# _check_local_path_dependencies
# ---------------------------------------------------------------------------


class TestCheckLocalPathDependencies:
    def test_no_pyproject_returns_empty(self, tmp_path: Path) -> None:
        result = _check_local_path_dependencies(tmp_path / "pyproject.toml")
        assert result == []

    def test_no_eval_dependencies_returns_empty(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "my-app"\ndependencies = ["requests>=2.0"]\n'
        )
        result = _check_local_path_dependencies(pyproject)
        assert result == []

    def test_git_sources_returns_empty(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "my-app"\n'
            'dependencies = ["azure-ai-evaluation @ git+https://github.com/example/repo"]\n'
        )
        result = _check_local_path_dependencies(pyproject)
        assert result == []

    def test_inline_file_url_detected(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "my-app"\n'
            'dependencies = [\n'
            '  "azure-ai-evaluation @ file:///home/user/local-pkg",\n'
            ']\n'
        )
        result = _check_local_path_dependencies(pyproject)
        assert "azure-ai-evaluation" in result

    def test_non_eval_packages_ignored(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "my-app"\n'
            'dependencies = [\n'
            '  "some-other-package @ file:///home/user/local",\n'
            ']\n'
        )
        result = _check_local_path_dependencies(pyproject)
        assert result == []

    def test_invalid_toml_returns_empty(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("this is not valid toml {{{{")
        result = _check_local_path_dependencies(pyproject)
        assert result == []

    def test_default_path_uses_cwd(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "my-app"\n'
            'dependencies = [\n'
            '  "azure-ai-evaluation @ file:///local/path",\n'
            ']\n'
        )
        result = _check_local_path_dependencies()
        assert "azure-ai-evaluation" in result


# ---------------------------------------------------------------------------
# _count_target_combinations
# ---------------------------------------------------------------------------


class TestCountTargetCombinations:
    def _make_target_cfg(self, args: Any = None) -> MagicMock:
        cfg = MagicMock()
        cfg.args = args
        return cfg

    def test_no_args(self) -> None:
        assert _count_target_combinations(self._make_target_cfg(None)) == 1

    def test_single_value(self) -> None:
        assert _count_target_combinations(self._make_target_cfg([{"temp": 0.7}])) == 1

    def test_list_values(self) -> None:
        assert _count_target_combinations(
            self._make_target_cfg([{"temp": [0.5, 0.7, 1.0]}])
        ) == 3

    def test_cartesian_product(self) -> None:
        cfg = self._make_target_cfg(
            [{"temp": [0.5, 1.0]}, {"tokens": [100, 200, 300]}]
        )
        assert _count_target_combinations(cfg) == 6  # 2 × 3


# ---------------------------------------------------------------------------
# run_preflight_checks
# ---------------------------------------------------------------------------


class TestRunPreflightChecks:
    @pytest.fixture()
    def mock_config(self) -> MagicMock:
        cfg = MagicMock()
        target_a = MagicMock()
        target_a.name = "target-a"
        target_a.args = [{"temp": 0.7}]
        cfg.experiment.targets = [target_a]
        return cfg

    def test_valid_config_passes(self, mock_config: MagicMock) -> None:
        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch(f"{_MOD}._count_target_combinations", return_value=1),
        ):
            MockConfig.from_yaml.return_value = mock_config

            # Should not raise or exit
            run_preflight_checks(
                config_path="config.yaml",
                interactive=False,
            )

    def test_zero_combinations_exits(self, mock_config: MagicMock) -> None:
        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch(f"{_MOD}._count_target_combinations", return_value=0),
        ):
            MockConfig.from_yaml.return_value = mock_config

            with pytest.raises(SystemExit) as exc_info:
                run_preflight_checks(
                    config_path="config.yaml",
                    interactive=False,
                )

            assert exc_info.value.code == 1

    def test_high_combo_count_warns_remote(
        self, mock_config: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        high_count = COMBINATION_COUNT_WARNING_THRESHOLD + 1
        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch(f"{_MOD}._count_target_combinations", return_value=high_count),
        ):
            MockConfig.from_yaml.return_value = mock_config

            with caplog.at_level("WARNING"):
                run_preflight_checks(
                    config_path="config.yaml",
                    interactive=False,
                    use_remote=True,
                )

            assert "High count" in caplog.text

    def test_invalid_target_filter_warns(
        self, mock_config: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch(f"{_MOD}._count_target_combinations", return_value=1),
        ):
            MockConfig.from_yaml.return_value = mock_config

            with caplog.at_level("WARNING"):
                run_preflight_checks(
                    config_path="config.yaml",
                    interactive=False,
                    target_filter=["target-a", "nonexistent-target"],
                )

            assert "nonexistent-target" in caplog.text

    def test_local_deps_on_remote_exits(self, mock_config: MagicMock) -> None:
        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch(f"{_MOD}._count_target_combinations", return_value=1),
            patch(
                f"{_MOD}._check_local_path_dependencies",
                return_value=["azure-ai-evaluation"],
            ),
        ):
            MockConfig.from_yaml.return_value = mock_config

            with pytest.raises(SystemExit) as exc_info:
                run_preflight_checks(
                    config_path="config.yaml",
                    interactive=False,
                    use_remote=True,
                )

            assert exc_info.value.code == 1

    def test_interactive_warns_prompts_user(self, mock_config: MagicMock) -> None:
        high_count = COMBINATION_COUNT_WARNING_THRESHOLD + 1
        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch(f"{_MOD}._count_target_combinations", return_value=high_count),
            patch("builtins.input", return_value="n"),
        ):
            MockConfig.from_yaml.return_value = mock_config

            with pytest.raises(SystemExit) as exc_info:
                run_preflight_checks(
                    config_path="config.yaml",
                    interactive=True,
                    use_remote=True,
                )

            assert exc_info.value.code == 130

    def test_interactive_warns_user_accepts(self, mock_config: MagicMock) -> None:
        high_count = COMBINATION_COUNT_WARNING_THRESHOLD + 1
        with (
            patch(f"{_MOD}.Config") as MockConfig,
            patch(f"{_MOD}._count_target_combinations", return_value=high_count),
            patch("builtins.input", return_value="y"),
        ):
            MockConfig.from_yaml.return_value = mock_config

            # Should not raise
            run_preflight_checks(
                config_path="config.yaml",
                interactive=True,
                use_remote=True,
            )


# ---------------------------------------------------------------------------
# CheckResult / CheckStatus
# ---------------------------------------------------------------------------


class TestCheckTypes:
    def test_check_status_values(self) -> None:
        assert CheckStatus.PASS.name == "PASS"
        assert CheckStatus.WARN.name == "WARN"
        assert CheckStatus.FAIL.name == "FAIL"

    def test_check_result_dataclass(self) -> None:
        r = CheckResult(name="Config", status=CheckStatus.PASS, message="OK")
        assert r.name == "Config"
        assert r.status == CheckStatus.PASS
        assert r.message == "OK"
