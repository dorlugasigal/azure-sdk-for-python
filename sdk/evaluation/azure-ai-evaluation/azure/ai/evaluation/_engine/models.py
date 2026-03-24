"""Data models for engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ExecutionContext:
    """Context provided to experiment components during execution."""

    connections_registry: Dict[str, Any] = field(default_factory=dict)
    experiment_name: str = ""
    experiment_version: str = ""
    experiment_dir: Optional[Path] = None
    output_path: str = ""
    tracking_enabled: bool = True
    model_variant_id: str = ""


@dataclass
class InferenceOutput:
    """Output of a model inference process."""

    output: Any
    model_name: str
    record: Dict[str, Any]
    args: Dict[str, Any]
    agent_trace: Any = None  # Optional AgentTrace from OTel trace capture

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (JSON-serializable)."""
        result = {
            "output": self.output,
            "model_name": self.model_name,
            "record": self.record,
            "args": self.args,
        }
        if self.agent_trace is not None:
            result["trace"] = {
                "trace_id": self.agent_trace.trace_id,
                "llm_call_count": len(self.agent_trace.llm_calls),
                "total_input_tokens": self.agent_trace.total_input_tokens,
                "total_output_tokens": self.agent_trace.total_output_tokens,
                "total_duration_ms": self.agent_trace.total_duration_ms,
                "tool_call_count": len(self.agent_trace.tool_calls),
            }
        return result


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
        """Convert to dictionary.

        Emits both 'evaluators' (new) and 'metrics' (Foundry compat) keys
        so results work in both our local viewer and the Foundry portal.
        """
        return {
            **self.inference_output.to_dict(),
            "run_id": self.run_id,
            "evaluators": self.evaluators,
            "metrics": self.evaluators,
            "system_evaluators": self.system_evaluators,
            "system_metrics": self.system_evaluators,
            "model_display_name": self.model_display_name,
            "metadata": self.metadata,
            "results": [r.to_dict() for r in self.results],
        }
