"""InferenceOutput data model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


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
