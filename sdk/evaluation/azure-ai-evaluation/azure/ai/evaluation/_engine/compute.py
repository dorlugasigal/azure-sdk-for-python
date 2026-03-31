"""Compute backend abstraction — controls WHERE evaluation runs."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Status of a submitted job."""
    SUBMITTED = "submitted"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobInfo:
    """Information about a submitted job."""
    job_id: str
    status: JobStatus
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunContext:
    """Context for running an evaluation job."""
    config_path: str
    env_path: Optional[str] = None
    dataset_path: Optional[str] = None
    model_filter: Optional[List[str]] = None


class ComputeBackend(ABC):
    """Abstract base for compute backends."""

    @abstractmethod
    def submit(self, context: RunContext, **kwargs: Any) -> JobInfo:
        """Submit an evaluation job. Returns JobInfo with status."""
        ...


class LocalComputeBackend(ComputeBackend):
    """Run evaluation synchronously in the current process."""

    def submit(self, context: RunContext, **kwargs: Any) -> JobInfo:
        logger.info(f"Starting local evaluation: {context.config_path}")
        try:
            from .evaluation.evaluator import ModelEvaluator

            # Show spinner during init (imports, target setup, evaluator registration)
            try:
                from rich.console import Console
                _con = Console()
                with _con.status("[bold cyan]Initializing targets and evaluators..."):
                    evaluator = ModelEvaluator(
                        config_path=context.config_path,
                        model_filter=context.model_filter,
                    )
                    dataset = evaluator.load_dataset(dataset_path=context.dataset_path)
            except ImportError:
                evaluator = ModelEvaluator(
                    config_path=context.config_path,
                    model_filter=context.model_filter,
                )
                dataset = evaluator.load_dataset(dataset_path=context.dataset_path)

            result = evaluator.evaluate(dataset)

            return JobInfo(
                job_id="local",
                status=JobStatus.COMPLETED,
                metadata={"execution_type": "local", **result},
            )
        except Exception as e:
            logger.exception("Local evaluation failed")
            return JobInfo(
                job_id="local",
                status=JobStatus.FAILED,
                metadata={"error": str(e), "execution_type": "local"},
            )


class FoundryComputeBackend(ComputeBackend):
    """Submit evaluation to Azure AI Foundry cloud compute."""

    def __init__(self, project_endpoint: str) -> None:
        self._project_endpoint = project_endpoint

    def submit(self, context: RunContext, **kwargs: Any) -> JobInfo:
        logger.info(f"Submitting to Foundry: {context.config_path}")
        try:
            from .foundry_compute import run_remote_evaluation

            result = run_remote_evaluation(
                config_path=context.config_path,
                project_endpoint=self._project_endpoint,
                on_progress=kwargs.get("on_progress"),
            )

            status = JobStatus.COMPLETED if result.get("status") == "completed" else JobStatus.FAILED
            return JobInfo(
                job_id=result.get("run_id", "foundry"),
                status=status,
                metadata={"execution_type": "foundry", **result},
            )
        except Exception as e:
            logger.exception("Foundry evaluation failed")
            return JobInfo(
                job_id="foundry",
                status=JobStatus.FAILED,
                metadata={"error": str(e), "execution_type": "foundry"},
            )
