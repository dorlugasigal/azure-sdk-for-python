"""Environment detection and validation for project-specific Python environments."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import List, Optional, TypedDict

import re

import yaml

# Regex for POSIX-style env var substitution: ${VAR}, ${VAR:-default}, ${VAR-default}
# Duplicated here to avoid importing config.py (which imports pydantic → heavy deps).
_ENV_VAR_PATTERN = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:(?P<op>:-|-)(?P<arg>.*?))?\}")

logger = logging.getLogger(__name__)

# Constants for environment detection
VENV_DIRECTORY_NAMES = (".venv", "venv", "env")
"""Virtual environment directory names to check, in priority order."""

SUBPROCESS_TIMEOUT_SECONDS = 5
"""Timeout for subprocess calls (e.g., checking Python version)."""


class EnvironmentInfo(TypedDict):
    """Type definition for environment information dictionary."""

    python_version: str
    engine_version: str
    env_type: str
    path: str


class ProjectEnvironmentError(Exception):
    """Raised when environment detection or validation fails."""


class EnvironmentResolver:
    """Auto-detect and validate Python environments for evaluation engine projects.

    Detection order:
    1. Explicit config override (if config_path provided -> runtime.python_executable)
    2. Project venv directories (.venv, venv, env)
    3. System Python (fallback)
    """

    def __init__(self) -> None:
        """Initialize the environment resolver."""
        self._warned_system_fallback = False

    def detect_python(
        self,
        project_path: str,
        config_path: Optional[str] = None,
        config_explicit: bool = False,
    ) -> str:
        """Detect the Python executable for a project.

        Args:
            project_path: Absolute path to the project directory.
            config_path: Optional absolute path to config file for python_executable override.
            config_explicit: Whether --config was explicitly provided (fail loudly on parse errors).

        Returns:
            Absolute path to the Python executable.

        Raises:
            ProjectEnvironmentError: If no valid Python environment is found.
        """
        project_path = os.path.abspath(project_path)

        # Try detection strategies in order
        python_exe = (
            self._check_config_override(config_path, config_explicit)
            or self._check_venv_dirs(project_path)
            or self._fallback_system_python()
        )

        if not os.path.isfile(python_exe):
            raise ProjectEnvironmentError(
                f"Detected Python executable does not exist: {python_exe}"
            )

        env_type = self._determine_env_type(project_path, python_exe)
        logger.debug("Detected Python environment: %s (%s)", env_type, python_exe)

        return python_exe

    def get_environment_info(
        self,
        project_path: str,
        config_path: Optional[str] = None,
        config_explicit: bool = False,
    ) -> EnvironmentInfo:
        """Get detailed information about the detected environment.

        Args:
            project_path: Absolute path to the project directory.
            config_path: Optional path to config file for python_executable override.
            config_explicit: Whether --config was explicitly provided.

        Returns:
            EnvironmentInfo with python_version, engine_version, env_type, and path.
        """
        python_exe = self.detect_python(
            project_path, config_path=config_path, config_explicit=config_explicit
        )

        python_version = self._get_python_version(python_exe)
        engine_version = self._get_package_version(
            python_exe, "azure.ai.evaluation"
        )

        # Determine environment type
        config_python = self._check_config_override(config_path, config_explicit=False)
        if config_python and config_python == python_exe:
            env_type = "config"
        else:
            env_type = self._determine_env_type(project_path, python_exe)

        return EnvironmentInfo(
            python_version=python_version,
            engine_version=engine_version,
            env_type=env_type,
            path=python_exe,
        )

    # ------------------------------------------------------------------
    # Env-var resolution
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_env_var(value: str) -> str:
        """Resolve POSIX-style env var references in a string.

        Supports: ``${VAR}``, ``${VAR:-default}``, ``${VAR-default}``

        Args:
            value: String potentially containing env var references.

        Returns:
            String with env vars resolved.

        Raises:
            ValueError: If a required env var (``${VAR}``) is missing.
        """
        import re  # noqa: F811 – local alias for the re.Match typing

        def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
            name = m.group("name")
            op = m.group("op")
            arg = m.group("arg") or ""

            is_set = name in os.environ
            v = os.environ.get(name, "")

            if op is None:
                if not is_set:
                    raise ValueError(f"Missing required env var: {name}")
                return v
            if op == ":-":
                return v if (is_set and v != "") else arg
            if op == "-":
                return v if is_set else arg

            return m.group(0)

        return _ENV_VAR_PATTERN.sub(_replace, value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_python_version(self, python_exe: str) -> str:
        """Get the Python version from an executable."""
        try:
            result = subprocess.run(
                [python_exe, "--version"],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
            return result.stdout.strip().replace("Python ", "")
        except Exception as e:
            logger.debug("Failed to get Python version: %s", e)
            return "unknown"

    def _get_package_version(self, python_exe: str, package_import: str) -> str:
        """Get a package version from a Python environment.

        Args:
            python_exe: Path to the Python executable.
            package_import: Dotted import path of the package (e.g. ``azure.ai.evaluation``).

        Returns:
            Version string, ``"not installed"``, or ``"unknown"``.
        """
        try:
            result = subprocess.run(
                [
                    python_exe,
                    "-c",
                    f"import {package_import}; print({package_import}.__version__)",
                ],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
            return result.stdout.strip() if result.returncode == 0 else "not installed"
        except Exception as e:
            logger.debug("Failed to get %s version: %s", package_import, e)
            return "unknown"

    def _check_config_override(
        self, config_path: Optional[str], config_explicit: bool = False
    ) -> Optional[str]:
        """Check for explicit Python executable in config file.

        Uses lightweight YAML parsing to extract only ``experiment.runtime.python_executable``
        without full config validation.
        """
        if not config_path or not os.path.isfile(config_path):
            return None

        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)

            if not data:
                return None

            experiment = data.get("experiment", {})
            runtime = experiment.get("runtime", {})
            python_exe_raw = runtime.get("python_executable")

            if not python_exe_raw:
                return None

            try:
                python_exe = self.resolve_env_var(python_exe_raw)
            except ValueError as e:
                raise ProjectEnvironmentError(
                    f"Failed to resolve environment variables in "
                    f"'experiment.runtime.python_executable': {e}. "
                    f"Please check the setting in {config_path}"
                ) from e

            if os.path.isfile(python_exe):
                logger.debug("Using Python executable from config override: %s", python_exe)
                return python_exe

            raise ProjectEnvironmentError(
                f"Configured Python executable at '{python_exe}' does not exist. "
                f"Please check the 'experiment.runtime.python_executable' setting "
                f"in {config_path}"
            )

        except ProjectEnvironmentError:
            raise
        except Exception as e:
            if config_explicit:
                raise ProjectEnvironmentError(
                    f"Failed to parse config file '{config_path}': {e}. "
                    f"Please check for YAML syntax errors or malformed structure."
                ) from e
            logger.warning(
                "Could not parse config '%s': %s. Falling back to auto-detection.",
                config_path,
                e,
            )

        return None

    def _check_venv_dirs(self, project_path: str) -> Optional[str]:
        """Check for common venv directory names.

        Checks directories in priority order: .venv, venv, env.
        Logs a warning if multiple virtual environments are found.
        """
        found_venvs: List[tuple] = []

        for venv_name in VENV_DIRECTORY_NAMES:
            venv_path = os.path.join(project_path, venv_name)
            if os.path.isdir(venv_path):
                python_exe = self._get_venv_python(venv_path)
                if python_exe and os.path.isfile(python_exe):
                    found_venvs.append((venv_name, python_exe))

        if not found_venvs:
            return None

        if len(found_venvs) > 1:
            venv_names = ", ".join(name for name, _ in found_venvs)
            logger.warning(
                "Multiple virtual environments found in %s: %s. Using %s.",
                project_path,
                venv_names,
                found_venvs[0][0],
            )

        return found_venvs[0][1]

    @staticmethod
    def _get_venv_python(venv_path: str) -> Optional[str]:
        """Get Python executable path from a venv directory (Windows + Unix)."""
        # Windows
        python_exe = os.path.join(venv_path, "Scripts", "python.exe")
        if os.path.isfile(python_exe):
            return python_exe

        # Unix
        python_exe = os.path.join(venv_path, "bin", "python")
        if os.path.isfile(python_exe):
            return python_exe

        return None

    def _fallback_system_python(self) -> str:
        """Fallback to the system Python (current interpreter)."""
        if not self._warned_system_fallback:
            logger.warning(
                "No project environment detected; using system Python. "
                "Set runtime.python_executable in config or create a venv "
                "to use a specific environment."
            )
            self._warned_system_fallback = True
        return sys.executable

    @staticmethod
    def _determine_env_type(project_path: str, python_exe: str) -> str:
        """Determine the type of environment based on the Python executable path.

        Returns:
            ``"venv"`` if inside a project virtual env, ``"system"`` otherwise.
        """
        for venv_name in VENV_DIRECTORY_NAMES:
            venv_path = os.path.join(project_path, venv_name)
            if python_exe.startswith(venv_path):
                return "venv"

        return "system"
