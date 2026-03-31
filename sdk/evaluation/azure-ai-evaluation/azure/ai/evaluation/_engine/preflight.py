"""Pre-flight checks for evaluation engine runs."""
from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum, auto
from itertools import product
from pathlib import Path
from typing import Dict, List, Optional

from .models.config import Config, TargetVariantConfig

logger = logging.getLogger(__name__)

COMBINATION_COUNT_WARNING_THRESHOLD = int(
    os.getenv("AZURE_AI_EVAL_COMBINATION_WARNING_THRESHOLD", "100")
)

# Only check for inline @ file:// URLs in dependencies.
_LOCAL_PATH_PATTERNS = [
    re.compile(r"@\s*file://", re.IGNORECASE),
]

# Packages whose local-path references would break on remote compute.
_EVALUATION_PACKAGE_PREFIXES = ("azure-ai-evaluation",)


# ------------------------------------------------------------------
# Local-path dependency check
# ------------------------------------------------------------------


def _check_local_path_dependencies(
    pyproject_path: Optional[Path] = None,
) -> List[str]:
    """Check pyproject.toml for local path dependencies that won't work on remote.

    Args:
        pyproject_path: Path to pyproject.toml. Defaults to ``./pyproject.toml``.

    Returns:
        List of dependency names that have local path references.
    """
    if pyproject_path is None:
        pyproject_path = Path("pyproject.toml")

    if not pyproject_path.exists():
        return []

    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return []

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return []

    local_deps: List[str] = []

    dependencies = data.get("project", {}).get("dependencies", [])
    for dep in dependencies:
        if not isinstance(dep, str):
            continue
        # Only check evaluation-related packages
        dep_lower = dep.lower()
        if not any(dep_lower.startswith(prefix) for prefix in _EVALUATION_PACKAGE_PREFIXES):
            continue
        for pattern in _LOCAL_PATH_PATTERNS:
            if pattern.search(dep):
                pkg_name = (
                    dep.split()[0]
                    .split("@")[0]
                    .split(">")[0]
                    .split("<")[0]
                    .split("=")[0]
                    .split("[")[0]
                )
                local_deps.append(pkg_name)
                break

    return local_deps


# ------------------------------------------------------------------
# Check result types
# ------------------------------------------------------------------


class CheckStatus(Enum):
    """Status of a single pre-flight check."""

    PASS = auto()
    WARN = auto()
    FAIL = auto()


@dataclass
class CheckResult:
    """Result of a single pre-flight check."""

    name: str
    status: CheckStatus
    message: str


# ------------------------------------------------------------------
# Combination counting
# ------------------------------------------------------------------


def _count_target_combinations(target_cfg: TargetVariantConfig) -> int:
    """Count the number of argument combinations for a single target.

    Mirrors the Cartesian-product logic in ``combination_utils.generate_args_combinations``
    without requiring a full evaluator instance.
    """
    if not target_cfg.args:
        return 1

    args_list = target_cfg.args if isinstance(target_cfg.args, list) else [target_cfg.args]

    arg_dicts: List[Dict[str, list]] = []
    for arg in args_list:
        if isinstance(arg, dict):
            for key, values in arg.items():
                if isinstance(values, list):
                    arg_dicts.append({key: values})
                else:
                    arg_dicts.append({key: [values]})

    if not arg_dicts:
        return 1

    keys = [list(d.keys())[0] for d in arg_dicts]
    value_lists = [list(d.values())[0] for d in arg_dicts]
    return len(list(product(*value_lists)))


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


def run_preflight_checks(
    config_path: str,
    interactive: bool,
    use_remote: bool = False,
    target_filter: Optional[List[str]] = None,
) -> None:
    """Run pre-flight checks and prompt user for confirmation if necessary.

    Args:
        config_path: Path to the configuration file.
        interactive: Whether to prompt the user for confirmation.
        use_remote: Whether the experiment is running on remote compute.
        target_filter: Optional list of target names to include.  If *None*, all
            targets are included.

    Raises:
        SystemExit: If checks fail or user declines confirmation.
    """
    config = Config.from_yaml(config_path)

    # -- Compute combination counts --
    total_count = 0
    configured_target_names: List[str] = []
    invalid_target_names: List[str] = []

    targets = getattr(config.experiment, "targets", []) or []

    configured_target_names = [
        getattr(t, "name", "Unknown") for t in targets
    ]

    if target_filter is not None:
        invalid_target_names = [
            name for name in target_filter if name not in configured_target_names
        ]

    logger.info("Target Combinations:")
    for target_cfg in targets:
        name = getattr(target_cfg, "name", "Unknown")

        # Skip targets not in filter (if filter is provided)
        if target_filter is not None and name not in target_filter:
            continue

        count = _count_target_combinations(target_cfg)
        total_count += count

        logger.info("  - %s: %d", name, count)

    logger.info("Total: %d", total_count)

    # -- Generate check results --
    def _generate_checks() -> Generator[CheckResult, None, None]:
        # Check 1: Configuration loaded successfully
        yield CheckResult("Configuration", CheckStatus.PASS, f"Loaded {config_path}")

        # Check 2: High combination count (warning only for remote)
        if use_remote and total_count > COMBINATION_COUNT_WARNING_THRESHOLD:
            yield CheckResult(
                "Combination Count",
                CheckStatus.WARN,
                f"High count: {total_count} combinations (Remote)",
            )

        # Check 4: Invalid target names in filter
        if invalid_target_names:
            yield CheckResult(
                "Target Filter",
                CheckStatus.WARN,
                f"Invalid target names in filter: {', '.join(invalid_target_names)}",
            )

        # Check 5: Zero combinations
        if total_count == 0:
            yield CheckResult(
                "Combination Count",
                CheckStatus.FAIL,
                "No target combinations found. Check configuration and filters.",
            )

        # Check 6: Local path dependencies (remote only)
        if use_remote:
            local_path_deps = _check_local_path_dependencies()
            if local_path_deps:
                yield CheckResult(
                    "Dependencies",
                    CheckStatus.FAIL,
                    f"Local path dependencies detected: {', '.join(local_path_deps)}. "
                    f"These won't resolve on remote compute.",
                )

    results = list(_generate_checks())

    # Only display non-PASS results
    visible_results = [r for r in results if r.status != CheckStatus.PASS]

    warning_count = sum(1 for r in visible_results if r.status == CheckStatus.WARN)
    error_count = sum(1 for r in visible_results if r.status == CheckStatus.FAIL)

    if visible_results:
        logger.info("Pre-flight Checks:")
        for result in visible_results:
            if result.status == CheckStatus.WARN:
                logger.warning("WARN %s: %s", result.name, result.message)
            else:
                logger.error("FAIL %s: %s", result.name, result.message)

    if error_count > 0:
        logger.error(
            "Pre-flight checks failed with %d error(s). Aborting.", error_count
        )
        sys.exit(1)

    if interactive and warning_count > 0:
        prompt = f"Do you want to proceed despite {warning_count} warning(s)? [Y/n] "
        try:
            answer = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer not in ("", "y", "yes"):
            logger.info("Evaluation cancelled by user.")
            sys.exit(130)  # 128 + SIGINT
