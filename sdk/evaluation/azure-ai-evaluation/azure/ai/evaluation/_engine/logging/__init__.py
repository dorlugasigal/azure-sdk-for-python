"""Logging utilities for the evaluation engine."""
from __future__ import annotations

from .logger import get_console, setup_logger
from .metrics_logger import LocalMetricsLogger

__all__ = [
    "get_console",
    "setup_logger",
    "LocalMetricsLogger",
]
