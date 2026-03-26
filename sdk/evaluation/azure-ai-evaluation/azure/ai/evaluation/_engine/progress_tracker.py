"""Progress tracking for evaluation runs."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _is_interactive_environment() -> bool:
    """Return ``True`` when Rich progress bars are appropriate.

    Falls back to simple logging when running inside Azure ML, CI, or
    when explicitly disabled via environment variables.
    """
    if os.getenv("AZURE_AI_EVAL_DISABLE_RICH", "false").lower() == "true":
        return False
    if os.getenv("IS_AZURE_ML", "false").lower() == "true":
        return False
    # Generic CI detection (GitHub Actions, Azure DevOps, Jenkins, etc.)
    if os.getenv("CI", "false").lower() == "true":
        return False
    return True


class ProgressTracker:
    """Unified progress tracker for evaluation runs.

    In interactive terminals it renders Rich progress bars; in CI / Azure ML
    it emits structured log messages at configurable intervals.

    Usage::

        with ProgressTracker(total_targets=2) as tracker:
            tracker.begin_target("gpt-4o", total_records=500)
            for record in dataset:
                process(record)
                tracker.advance()
            tracker.finish_target()
    """

    def __init__(
        self,
        total_targets: int,
        *,
        log_interval_pct: int = 10,
        console: Optional[Any] = None,
    ) -> None:
        """
        Args:
            total_targets: Number of targets (models) to evaluate.
            log_interval_pct: Percentage interval for non-interactive progress
                logging (e.g. 10 means log at every ~10 %).
            console: Optional Rich ``Console`` for interactive output.
        """
        self._total_targets = total_targets
        self._log_interval_pct = max(1, log_interval_pct)
        self._console = console
        self._is_interactive = _is_interactive_environment()

        # Rich progress state (lazy-initialised on __enter__)
        self._progress: Any = None
        self._targets_task: Any = None
        self._current_task: Any = None

        # Logging-based progress state
        self._completed_targets = 0
        self._current_target = ""
        self._total_records = 0
        self._completed_records = 0

    # -- context manager --------------------------------------------------

    def __enter__(self) -> ProgressTracker:
        if self._is_interactive:
            try:
                from rich.console import Console as RichConsole
                from rich.progress import (
                    BarColumn,
                    MofNCompleteColumn,
                    Progress,
                    SpinnerColumn,
                    TextColumn,
                    TimeElapsedColumn,
                    TimeRemainingColumn,
                )

                if self._console is None:
                    self._console = RichConsole()

                self._progress = Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("records:"),
                    MofNCompleteColumn(),
                    TextColumn("elapsed:"),
                    TimeElapsedColumn(),
                    TextColumn("remaining:"),
                    TimeRemainingColumn(),
                    console=self._console,
                )
                self._progress.__enter__()
                self._targets_task = self._progress.add_task(
                    "Evaluating targets", total=self._total_targets
                )
            except ImportError:
                # Rich not installed — silently fall back to logging
                self._is_interactive = False
                logger.info(
                    "Rich is not installed; falling back to simple progress logging."
                )

        if not self._is_interactive:
            logger.info(
                "Running in non-interactive mode — using simple progress logging."
            )

        return self

    def __exit__(self, *args: Any) -> None:
        if self._progress is not None:
            self._progress.__exit__(*args)

    # -- public API --------------------------------------------------------

    def begin_target(self, target_name: str, total_records: int) -> None:
        """Start tracking a new target.

        Args:
            target_name: Display name of the target being evaluated.
            total_records: Number of records to process for this target.
        """
        self._current_target = target_name
        self._total_records = total_records
        self._completed_records = 0

        if self._is_interactive and self._progress is not None:
            self._current_task = self._progress.add_task(
                f"Evaluating target {target_name}", total=total_records
            )
        else:
            logger.info(
                "Starting target %d/%d: %s (%d records)",
                self._completed_targets + 1,
                self._total_targets,
                target_name,
                total_records,
            )

    def advance(self) -> None:
        """Record one completed record."""
        self._completed_records += 1

        if self._is_interactive and self._progress is not None:
            self._progress.update(self._current_task, advance=1)
        else:
            interval = max(1, self._total_records * self._log_interval_pct // 100)
            if (
                self._completed_records % interval == 0
                or self._completed_records == self._total_records
            ):
                if self._total_records <= 0:
                    logger.info(
                        "  Progress: %d records (total unknown)",
                        self._completed_records,
                    )
                else:
                    pct = (self._completed_records / self._total_records) * 100
                    logger.info(
                        "  Progress: %d/%d records (%.1f%%)",
                        self._completed_records,
                        self._total_records,
                        pct,
                    )

    def finish_target(self) -> None:
        """Mark the current target as complete."""
        self._completed_targets += 1

        if self._is_interactive and self._progress is not None:
            self._progress.update(self._targets_task, advance=1)
        else:
            logger.info(
                "Completed %s (%d/%d records)",
                self._current_target,
                self._completed_records,
                self._total_records,
            )
            logger.info(
                "Overall: %d/%d targets completed",
                self._completed_targets,
                self._total_targets,
            )
