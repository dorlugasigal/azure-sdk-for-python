"""Factory for creating tracking backends from config."""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Config

from .backend import TrackingBackend
from .noop import NoOpFallbackBackend


def create_tracking_backend(
    config: Optional[Any] = None,
    tracking_enabled: bool = True,
) -> TrackingBackend:
    """Create tracking backend from config.

    Args:
        config: Full Config object (reads experiment.tracking_backend)
        tracking_enabled: If False, always returns NoOpFallbackBackend

    Returns:
        TrackingBackend instance
    """
    if not tracking_enabled or config is None:
        return NoOpFallbackBackend()

    tracking_config = None
    if hasattr(config, "experiment"):
        tracking_config = getattr(config.experiment, "tracking_backend", None)

    if not tracking_config:
        return NoOpFallbackBackend()

    backend_type = getattr(tracking_config, "type", "none")

    if backend_type == "none" or not backend_type:
        return NoOpFallbackBackend()

    if backend_type == "foundry":
        try:
            from .foundry_backend import FoundryTrackingBackend  # type: ignore[import-not-found]

            config_dict = (
                tracking_config.model_dump()
                if hasattr(tracking_config, "model_dump")
                else dict(tracking_config)
            )
            return FoundryTrackingBackend(config=config_dict)
        except ImportError:
            return NoOpFallbackBackend()

    raise ValueError(
        f"Unknown tracking backend type: '{backend_type}'. "
        f"Available: none, foundry"
    )
