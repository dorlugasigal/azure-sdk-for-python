"""Rich-aware logging with fallback to plain stream handlers.

Provides dual-handler logging (console + file) with thread-safe console
sharing.  The console handler uses Rich when available and falls back to
a plain ``StreamHandler`` when Rich is disabled or unavailable.

Environment variables
---------------------
``LOG_LEVEL``
    Python log-level name (default ``"INFO"``).
``LOG_PATH``
    Directory for the log file (default ``"logs"``).
``EVEE_DISABLE_RICH_LOGGING``
    Set to ``"true"`` to force plain-text console output.
``IS_AZURE_ML``
    Set to ``"true"`` when running inside Azure ML (disables Rich).
``EVEE_MCP_MODE``
    Set to ``"true"`` when running in MCP mode (disables Rich).
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

DEFAULT_LOGGER_NAME = "model_evaluation"
DEFAULT_LOG_DIR = "logs"
LOG_FILE_NAME = "model_evaluation.log"

_shared_console: object | None = None
_console_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Rich-compatibility detection (inlined to avoid external util dependency)
# ---------------------------------------------------------------------------

def _is_rich_compatible_environment() -> bool:
    """Return *True* when Rich console output should be used.

    Rich is disabled when any of the following environment variables is
    set to ``"true"`` (case-insensitive):

    * ``EVEE_DISABLE_RICH_LOGGING``
    * ``IS_AZURE_ML``
    * ``EVEE_MCP_MODE``
    """
    if os.getenv("EVEE_DISABLE_RICH_LOGGING", "false").lower() == "true":
        return False
    if os.getenv("EVEE_MCP_MODE", "false").lower() == "true":
        return False
    if os.getenv("IS_AZURE_ML", "false").lower() == "true":
        return False
    return True


def _rich_available() -> bool:
    """Return *True* if the ``rich`` package is importable."""
    try:
        import rich  # noqa: F401
        return True
    except ImportError:
        return False


def _use_rich() -> bool:
    """Return *True* when Rich should actually be used (compatible **and** installed)."""
    return _is_rich_compatible_environment() and _rich_available()


# ---------------------------------------------------------------------------
# Shared console
# ---------------------------------------------------------------------------

def get_console():
    """Get or create the shared Rich ``Console`` instance.

    Returns ``None`` when Rich is not available.
    """
    global _shared_console
    if not _use_rich():
        return None
    with _console_lock:
        if _shared_console is None:
            from rich.console import Console
            _shared_console = Console(force_terminal=True)
    return _shared_console


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_log_level() -> int:
    name = os.getenv("LOG_LEVEL", "INFO").upper()
    return logging.getLevelNamesMapping().get(name, logging.INFO)


def _create_console_handler(level: int, console: Optional[object] = None) -> logging.Handler:
    if _use_rich():
        from rich.logging import RichHandler
        if console is None:
            console = get_console()
        handler: logging.Handler = RichHandler(rich_tracebacks=True, console=console)
    else:
        handler = logging.StreamHandler()

    handler.setLevel(level)
    return handler


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logger(
    logger_name: str = DEFAULT_LOGGER_NAME,
    logs_path: str = DEFAULT_LOG_DIR,
    *,
    force: bool = False,
    console: Optional[object] = None,
) -> logging.Logger:
    """Create (or retrieve) a logger with console and file handlers.

    Parameters
    ----------
    logger_name:
        Name passed to :func:`logging.getLogger`.
    logs_path:
        Default directory for the log file (overridden by ``LOG_PATH``).
    force:
        When *True*, clear existing handlers and re-configure.
    console:
        Optional Rich ``Console`` instance for the console handler.

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    level = _get_log_level()
    log_dir = Path(os.getenv("LOG_PATH", logs_path))
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    if logger.hasHandlers() and not force:
        return logger

    if force:
        logger.handlers.clear()

    use_rich = _use_rich()
    console_fmt = (
        logging.Formatter("%(message)s")
        if use_rich
        else logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    if console is None:
        console = get_console()

    console_handler = _create_console_handler(level, console=console)
    console_handler.setFormatter(console_fmt)

    file_fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(log_dir / LOG_FILE_NAME)
    file_handler.setLevel(level)
    file_handler.setFormatter(file_fmt)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger
