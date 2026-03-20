"""Constants and enums for tracking backends.

Use these instead of magic strings for type safety.
"""

from __future__ import annotations

from enum import Enum


class OperationStatus(str, Enum):
    """Status values for operations (runs, inferences, etc.)."""

    SUCCESS = "success"
    FAILED = "failed"
