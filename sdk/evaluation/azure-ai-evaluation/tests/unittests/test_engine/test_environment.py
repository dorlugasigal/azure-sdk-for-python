# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for EnvironmentResolver."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from azure.ai.evaluation._engine.environment import (
    EnvironmentResolver,
    ProjectEnvironmentError,
    VENV_DIRECTORY_NAMES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def resolver() -> EnvironmentResolver:
    return EnvironmentResolver()


@pytest.fixture()
def mock_project(tmp_path: Path) -> Path:
    """Temporary project directory."""
    project = tmp_path / "test_project"
    project.mkdir()
    return project


# ---------------------------------------------------------------------------
# Venv detection
# ---------------------------------------------------------------------------


class TestVenvDetection:
    def test_detect_venv_directory(
        self, resolver: EnvironmentResolver, mock_project: Path
    ) -> None:
        venv_dir = mock_project / ".venv" / "bin"
        venv_dir.mkdir(parents=True)
        python_exe = venv_dir / "python"
        python_exe.touch()

        detected = resolver.detect_python(str(mock_project))
        assert detected == str(python_exe)

    def test_detect_venv_priority_order(
        self, resolver: EnvironmentResolver, tmp_path: Path
    ) -> None:
        """`.venv` takes priority over `venv`."""
        project = tmp_path / "project"
        project.mkdir()

        for name in (".venv", "venv"):
            bin_dir = project / name / "bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "python").touch()

        detected = resolver.detect_python(str(project))
        assert "/.venv/" in detected

    def test_detect_venv_windows(
        self, resolver: EnvironmentResolver, tmp_path: Path
    ) -> None:
        """Windows-style Scripts/python.exe path."""
        project = tmp_path / "project"
        project.mkdir()
        scripts_dir = project / ".venv" / "Scripts"
        scripts_dir.mkdir(parents=True)
        python_exe = scripts_dir / "python.exe"
        python_exe.touch()

        detected = resolver.detect_python(str(project))
        assert detected == str(python_exe)

    def test_multiple_venvs_warns(
        self,
        resolver: EnvironmentResolver,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        project = tmp_path / "project"
        project.mkdir()

        for name in (".venv", "venv"):
            bin_dir = project / name / "bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "python").touch()

        with caplog.at_level("WARNING"):
            resolver.detect_python(str(project))

        assert "Multiple virtual environments" in caplog.text


# ---------------------------------------------------------------------------
# Config override
# ---------------------------------------------------------------------------


class TestConfigOverride:
    def test_config_override(
        self, resolver: EnvironmentResolver, tmp_path: Path
    ) -> None:
        project = tmp_path / "project"
        project.mkdir()

        config_data = {
            "experiment": {
                "runtime": {"python_executable": "/usr/bin/python3"}
            }
        }
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump(config_data))

        with patch("os.path.isfile", return_value=True):
            detected = resolver.detect_python(
                str(project), config_path=str(config_path)
            )

        assert detected == "/usr/bin/python3"

    def test_config_override_nonexistent_raises(
        self, resolver: EnvironmentResolver, tmp_path: Path
    ) -> None:
        project = tmp_path / "project"
        project.mkdir()

        config_data = {
            "experiment": {
                "runtime": {"python_executable": "/nonexistent/python"}
            }
        }
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump(config_data))

        with pytest.raises(ProjectEnvironmentError, match="does not exist"):
            resolver.detect_python(str(project), config_path=str(config_path))

    def test_config_override_with_env_var(
        self, resolver: EnvironmentResolver, tmp_path: Path
    ) -> None:
        project = tmp_path / "project"
        project.mkdir()

        config_data = {
            "experiment": {
                "runtime": {"python_executable": "${MY_PYTHON_PATH}"}
            }
        }
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump(config_data))

        with (
            patch.dict(os.environ, {"MY_PYTHON_PATH": "/custom/python"}),
            patch("os.path.isfile", return_value=True),
        ):
            detected = resolver.detect_python(
                str(project), config_path=str(config_path)
            )

        assert detected == "/custom/python"

    def test_config_parse_error_explicit_raises(
        self, resolver: EnvironmentResolver, tmp_path: Path
    ) -> None:
        project = tmp_path / "project"
        project.mkdir()

        config_path = tmp_path / "config.yaml"
        config_path.write_text(": invalid: yaml: {{}")

        with pytest.raises(ProjectEnvironmentError, match="Failed to parse"):
            resolver.detect_python(
                str(project), config_path=str(config_path), config_explicit=True
            )

    def test_config_parse_error_implicit_warns(
        self,
        resolver: EnvironmentResolver,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        project = tmp_path / "project"
        project.mkdir()

        # Create a config that will cause a non-YAML parse error
        # by making the runtime.python_executable contain an unresolvable env var
        config_path = tmp_path / "config.yaml"
        config_path.write_text(": invalid: yaml: {{}")

        # With config_explicit=False, it should warn and fall back
        with caplog.at_level("WARNING"):
            # Will fall back to system python since no venv exists
            detected = resolver.detect_python(
                str(project), config_path=str(config_path), config_explicit=False
            )

        assert "Could not parse" in caplog.text
        assert detected == sys.executable


# ---------------------------------------------------------------------------
# System fallback
# ---------------------------------------------------------------------------


class TestSystemFallback:
    def test_fallback_to_system_python(
        self, resolver: EnvironmentResolver, tmp_path: Path
    ) -> None:
        project = tmp_path / "empty_project"
        project.mkdir()

        detected = resolver.detect_python(str(project))
        assert detected == sys.executable

    def test_fallback_warns_once(
        self,
        resolver: EnvironmentResolver,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        project = tmp_path / "empty_project"
        project.mkdir()

        with caplog.at_level("WARNING"):
            resolver.detect_python(str(project))
            resolver.detect_python(str(project))

        # Warning emitted only once
        assert caplog.text.count("No project environment detected") == 1


# ---------------------------------------------------------------------------
# resolve_env_var
# ---------------------------------------------------------------------------


class TestResolveEnvVar:
    def test_required_var(self) -> None:
        with patch.dict(os.environ, {"FOO": "bar"}):
            assert EnvironmentResolver.resolve_env_var("${FOO}") == "bar"

    def test_required_var_missing_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Missing required env var"):
                EnvironmentResolver.resolve_env_var("${MISSING_VAR}")

    def test_default_value_colon_dash(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert EnvironmentResolver.resolve_env_var("${X:-fallback}") == "fallback"

    def test_default_value_dash(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert EnvironmentResolver.resolve_env_var("${X-fallback}") == "fallback"

    def test_colon_dash_uses_default_on_empty(self) -> None:
        with patch.dict(os.environ, {"X": ""}):
            assert EnvironmentResolver.resolve_env_var("${X:-fallback}") == "fallback"

    def test_dash_keeps_empty(self) -> None:
        with patch.dict(os.environ, {"X": ""}):
            assert EnvironmentResolver.resolve_env_var("${X-fallback}") == ""

    def test_no_env_var(self) -> None:
        assert EnvironmentResolver.resolve_env_var("plain text") == "plain text"


# ---------------------------------------------------------------------------
# get_environment_info
# ---------------------------------------------------------------------------


class TestGetEnvironmentInfo:
    def test_returns_all_fields(
        self, resolver: EnvironmentResolver, mock_project: Path
    ) -> None:
        venv_dir = mock_project / ".venv" / "bin"
        venv_dir.mkdir(parents=True)
        python_exe = venv_dir / "python"
        python_exe.touch()

        with (
            patch.object(resolver, "_get_python_version", return_value="3.11.5"),
            patch.object(
                resolver, "_get_package_version", return_value="1.0.0"
            ),
        ):
            info = resolver.get_environment_info(str(mock_project))

        assert info["python_version"] == "3.11.5"
        assert info["engine_version"] == "1.0.0"
        assert info["env_type"] == "venv"
        assert info["path"] == str(python_exe)


# ---------------------------------------------------------------------------
# _determine_env_type
# ---------------------------------------------------------------------------


class TestDetermineEnvType:
    def test_venv_type(self, tmp_path: Path) -> None:
        project = str(tmp_path / "project")
        python = os.path.join(project, ".venv", "bin", "python")
        assert EnvironmentResolver._determine_env_type(project, python) == "venv"

    def test_system_type(self, tmp_path: Path) -> None:
        project = str(tmp_path / "project")
        python = "/usr/bin/python3"
        assert EnvironmentResolver._determine_env_type(project, python) == "system"
