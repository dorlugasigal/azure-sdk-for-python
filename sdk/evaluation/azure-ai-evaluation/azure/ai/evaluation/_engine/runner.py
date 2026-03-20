"""ExperimentRunner — orchestrates evaluation with compute + tracking separation."""
from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

from .compute import (
    ComputeBackend,
    FoundryComputeBackend,
    JobInfo,
    JobStatus,
    LocalComputeBackend,
    RunContext,
)
from .config import Config

logger = logging.getLogger(__name__)


class ExperimentRunner:
    """Orchestrates evaluation: selects compute backend, builds context, submits job.

    Usage:
        runner = ExperimentRunner()
        job_info = runner.run(
            config_path="evals.yaml",
            remote_compute=False,
            tracking_enabled=True,
        )
    """

    def run(
        self,
        config_path: str,
        env_path: Optional[str] = None,
        dataset_path: Optional[str] = None,
        remote_compute: bool = False,
        tracking_enabled: bool = True,
        model_filter: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> JobInfo:
        """Run an evaluation experiment.

        Args:
            config_path: Path to YAML config file
            env_path: Optional path to .env file
            dataset_path: Optional override for dataset path
            remote_compute: If True, submit to configured remote compute backend
            tracking_enabled: If True, enable tracking backend
            model_filter: Optional list of model names to evaluate

        Returns:
            JobInfo with status and metadata
        """
        # Load .env if provided
        if env_path and os.path.exists(env_path):
            try:
                from dotenv import load_dotenv
                load_dotenv(dotenv_path=env_path, override=True)
            except ImportError:
                pass

        # Load config to determine backend
        config = Config.from_yaml(config_path)

        # Select compute backend
        backend = self._select_backend(config, remote_compute)

        # Build run context
        context = RunContext(
            config_path=config_path,
            env_path=env_path,
            dataset_path=dataset_path,
            tracking_enabled=tracking_enabled,
            model_filter=model_filter,
        )

        logger.info(f"Running with {type(backend).__name__}")
        return backend.submit(context, **kwargs)

    def _select_backend(self, config: Config, remote_compute: bool) -> ComputeBackend:
        """Select compute backend based on config and --remote flag."""
        compute_config = getattr(config.experiment, "compute", None)

        if remote_compute:
            # User explicitly requested remote
            if compute_config and compute_config.azure_ai_project:
                return FoundryComputeBackend(
                    project_endpoint=compute_config.azure_ai_project,
                )

            # Try to find endpoint from connections
            for conn in (config.experiment.connections or []):
                endpoint = getattr(conn, "azure_ai_project", None)
                if endpoint:
                    return FoundryComputeBackend(project_endpoint=endpoint)

            raise ValueError(
                "Remote compute requested (--remote) but no project endpoint configured. "
                "Set 'compute.azure_ai_project' in your config or add a connection with an endpoint."
            )

        # Default: always local unless --remote was explicitly requested
        return LocalComputeBackend()
