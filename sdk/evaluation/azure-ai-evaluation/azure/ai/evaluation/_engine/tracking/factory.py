"""Factory for creating tracking backends from config."""

from __future__ import annotations

import logging
from typing import Any, Optional

from .backend import TrackingBackend
from .noop import NoOpFallbackBackend

logger = logging.getLogger(__name__)


def create_tracking_backend(
    config: Optional[Any] = None,
    tracking_enabled: bool = True,
) -> TrackingBackend:
    """Create tracking backend from config.

    Args:
        config: Full Config object. If provided, the tracking backend type
            is read from ``config.experiment.tracking_backend.type``.
        tracking_enabled: If False, always returns NoOpFallbackBackend
            without any warning.

    Returns:
        NoOpFallbackBackend (only backend currently available)
    """
    if not tracking_enabled:
        return NoOpFallbackBackend()

    tracking_type = _get_tracking_type(config)

    if tracking_type == "foundry":
        logger.warning(
            "Foundry tracking is not yet supported. Results will not be "
            "published to Foundry. Use --remote to run evaluations on "
            "Foundry compute instead."
        )

    return NoOpFallbackBackend()


def _get_tracking_type(config: Optional[Any]) -> Optional[str]:
    """Safely extract the tracking backend type from a config object."""
    try:
        return config.experiment.tracking_backend.type  # type: ignore[union-attr]
    except AttributeError:
        return None
