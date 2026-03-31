"""EvaluationOutput and EvaluatorResult data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models.inference_output import InferenceOutput


@dataclass
class EvaluatorResult:
    """Single evaluator result in Foundry-compatible format."""

    name: str
    score: Optional[float] = None
    label: Optional[str] = None  # "pass" or "fail"
    reason: Optional[str] = None
    threshold: Optional[float] = None
    passed: Optional[bool] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "score": self.score,
            "label": self.label,
            "reason": self.reason,
            "threshold": self.threshold,
            "passed": self.passed,
            "details": self.details,
        }


@dataclass
class EvaluationOutput:
    """Output of a model evaluation process."""

    run_id: str
    inference_output: InferenceOutput
    evaluators: Dict[str, Dict[str, Any]]
    system_evaluators: Dict[str, Dict[str, Any]]
    model_display_name: str
    metadata: Dict[str, Any]
    results: List[EvaluatorResult] = field(default_factory=list)  # Foundry-aligned per-evaluator results

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            **self.inference_output.to_dict(),
            "run_id": self.run_id,
            "evaluators": self.evaluators,
            "system_evaluators": self.system_evaluators,
            "model_display_name": self.model_display_name,
            "metadata": self.metadata,
            "results": [r.to_dict() for r in self.results],
        }
