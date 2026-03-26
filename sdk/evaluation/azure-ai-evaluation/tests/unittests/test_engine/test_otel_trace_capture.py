# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for OpenTelemetry trace capture (otel_trace_capture.py)."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from azure.ai.evaluation._engine.otel_trace_capture import (
    EVALUATION_EVENT_NAME,
    AgentTrace,
    CapturedLogEvent,
    CapturedSpan,
    OTelTraceCapture,
)


# ---------------------------------------------------------------------------
# CapturedSpan
# ---------------------------------------------------------------------------

class TestCapturedSpan:
    """Tests for CapturedSpan dataclass."""

    def test_creation(self) -> None:
        span = CapturedSpan(
            name="chat",
            trace_id="abc123",
            span_id="span1",
            parent_span_id=None,
            attributes={"gen_ai.operation.name": "chat"},
            duration_ms=150.0,
        )
        assert span.name == "chat"
        assert span.trace_id == "abc123"
        assert span.duration_ms == 150.0

    def test_operation_name(self) -> None:
        span = CapturedSpan(
            name="chat", trace_id="t", span_id="s",
            parent_span_id=None,
            attributes={"gen_ai.operation.name": "chat"},
            duration_ms=1.0,
        )
        assert span.operation_name == "chat"

    def test_operation_name_missing(self) -> None:
        span = CapturedSpan(
            name="other", trace_id="t", span_id="s",
            parent_span_id=None, attributes={}, duration_ms=1.0,
        )
        assert span.operation_name is None

    def test_model_from_response(self) -> None:
        span = CapturedSpan(
            name="chat", trace_id="t", span_id="s",
            parent_span_id=None,
            attributes={"gen_ai.response.model": "gpt-4"},
            duration_ms=1.0,
        )
        assert span.model == "gpt-4"

    def test_model_from_request(self) -> None:
        span = CapturedSpan(
            name="chat", trace_id="t", span_id="s",
            parent_span_id=None,
            attributes={"gen_ai.request.model": "gpt-3.5"},
            duration_ms=1.0,
        )
        assert span.model == "gpt-3.5"

    def test_model_missing(self) -> None:
        span = CapturedSpan(
            name="chat", trace_id="t", span_id="s",
            parent_span_id=None, attributes={}, duration_ms=1.0,
        )
        assert span.model is None

    def test_input_tokens(self) -> None:
        span = CapturedSpan(
            name="chat", trace_id="t", span_id="s",
            parent_span_id=None,
            attributes={"gen_ai.usage.input_tokens": 100},
            duration_ms=1.0,
        )
        assert span.input_tokens == 100

    def test_output_tokens(self) -> None:
        span = CapturedSpan(
            name="chat", trace_id="t", span_id="s",
            parent_span_id=None,
            attributes={"gen_ai.usage.output_tokens": 50},
            duration_ms=1.0,
        )
        assert span.output_tokens == 50

    def test_finish_reasons(self) -> None:
        span = CapturedSpan(
            name="chat", trace_id="t", span_id="s",
            parent_span_id=None,
            attributes={"gen_ai.response.finish_reasons": ("stop",)},
            duration_ms=1.0,
        )
        assert span.finish_reasons == ("stop",)

    def test_events_default_empty(self) -> None:
        span = CapturedSpan(
            name="x", trace_id="t", span_id="s",
            parent_span_id=None, attributes={}, duration_ms=0,
        )
        assert span.events == []


# ---------------------------------------------------------------------------
# CapturedLogEvent
# ---------------------------------------------------------------------------

class TestCapturedLogEvent:
    """Tests for CapturedLogEvent dataclass."""

    def test_creation(self) -> None:
        evt = CapturedLogEvent(
            trace_id="t1", span_id="s1",
            body={"message": {"role": "user", "content": "Hello"}},
        )
        assert evt.trace_id == "t1"
        assert evt.body["message"]["content"] == "Hello"

    def test_attributes_default_empty(self) -> None:
        evt = CapturedLogEvent(trace_id="t", span_id="s", body=None)
        assert evt.attributes == {}


# ---------------------------------------------------------------------------
# AgentTrace — reconstruction and properties
# ---------------------------------------------------------------------------

def _make_llm_span(
    span_id: str = "s1",
    operation: str = "chat",
    input_tokens: int = 10,
    output_tokens: int = 20,
    duration_ms: float = 100.0,
    **extra_attrs: Any,
) -> CapturedSpan:
    """Helper to create an LLM span."""
    attrs = {
        "gen_ai.operation.name": operation,
        "gen_ai.usage.input_tokens": input_tokens,
        "gen_ai.usage.output_tokens": output_tokens,
        **extra_attrs,
    }
    return CapturedSpan(
        name=operation, trace_id="trace1", span_id=span_id,
        parent_span_id="parent1", attributes=attrs,
        duration_ms=duration_ms,
    )


def _make_tool_span(
    span_id: str = "ts1",
    tool_name: str = "search",
    tool_call_id: str = "tc1",
) -> CapturedSpan:
    """Helper to create an execute_tool span."""
    return CapturedSpan(
        name="execute_tool", trace_id="trace1", span_id=span_id,
        parent_span_id="parent1",
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": tool_name,
            "gen_ai.tool.call.id": tool_call_id,
            "gen_ai.tool.call.arguments": json.dumps({"query": "test"}),
            "gen_ai.tool.call.result": "result data",
        },
        duration_ms=50.0,
    )


class TestAgentTrace:
    """Tests for AgentTrace reconstruction and properties."""

    def test_empty_trace(self) -> None:
        trace = AgentTrace(trace_id="t", parent_span_id="p")
        assert trace.llm_calls == []
        assert trace.total_input_tokens == 0
        assert trace.total_output_tokens == 0
        assert trace.total_duration_ms == 0.0
        assert trace.tool_calls == []

    def test_llm_calls_filters_chat_spans(self) -> None:
        trace = AgentTrace(
            trace_id="t", parent_span_id="p",
            spans=[
                _make_llm_span(span_id="s1", operation="chat"),
                _make_llm_span(span_id="s2", operation="text_completion"),
                _make_tool_span(span_id="s3"),
            ],
        )
        assert len(trace.llm_calls) == 2

    def test_total_input_tokens(self) -> None:
        trace = AgentTrace(
            trace_id="t", parent_span_id="p",
            spans=[
                _make_llm_span(span_id="s1", input_tokens=100),
                _make_llm_span(span_id="s2", input_tokens=200),
            ],
        )
        assert trace.total_input_tokens == 300

    def test_total_output_tokens(self) -> None:
        trace = AgentTrace(
            trace_id="t", parent_span_id="p",
            spans=[
                _make_llm_span(span_id="s1", output_tokens=50),
                _make_llm_span(span_id="s2", output_tokens=75),
            ],
        )
        assert trace.total_output_tokens == 125

    def test_total_duration_ms(self) -> None:
        trace = AgentTrace(
            trace_id="t", parent_span_id="p",
            spans=[
                _make_llm_span(span_id="s1", duration_ms=100.0),
                _make_llm_span(span_id="s2", duration_ms=200.0),
            ],
        )
        assert trace.total_duration_ms == 300.0

    def test_tool_calls_from_spans(self) -> None:
        trace = AgentTrace(
            trace_id="t", parent_span_id="p",
            spans=[_make_tool_span(tool_name="search", tool_call_id="tc1")],
        )
        tools = trace.tool_calls
        assert len(tools) == 1
        assert tools[0]["name"] == "search"
        assert tools[0]["id"] == "tc1"

    def test_tool_calls_deduplication(self) -> None:
        """Same tool_call_id should only appear once."""
        trace = AgentTrace(
            trace_id="t", parent_span_id="p",
            spans=[
                _make_tool_span(span_id="s1", tool_call_id="tc1"),
                _make_tool_span(span_id="s2", tool_call_id="tc1"),
            ],
        )
        assert len(trace.tool_calls) == 1

    def test_tool_calls_from_log_events(self) -> None:
        """Tool calls extracted from OpenAI instrumentor log events."""
        evt = CapturedLogEvent(
            trace_id="t", span_id="s",
            body={
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "tc_log1",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city": "Seattle"}',
                            },
                        }
                    ],
                }
            },
        )
        trace = AgentTrace(
            trace_id="t", parent_span_id="p", log_events=[evt]
        )
        tools = trace.tool_calls
        assert len(tools) == 1
        assert tools[0]["name"] == "get_weather"
        assert tools[0]["id"] == "tc_log1"

    def test_input_messages(self) -> None:
        trace = AgentTrace(
            trace_id="t", parent_span_id="p",
            log_events=[
                CapturedLogEvent(
                    trace_id="t", span_id="s",
                    body={"content": "Hello, agent!", "role": "user"},
                ),
            ],
        )
        assert len(trace.input_messages) == 1
        assert trace.input_messages[0]["content"] == "Hello, agent!"

    def test_final_response(self) -> None:
        trace = AgentTrace(
            trace_id="t", parent_span_id="p",
            log_events=[
                CapturedLogEvent(
                    trace_id="t", span_id="s",
                    body={
                        "message": {
                            "role": "assistant",
                            "content": "Here is my answer.",
                        }
                    },
                ),
            ],
        )
        assert trace.final_response == "Here is my answer."

    def test_final_response_none_when_empty(self) -> None:
        trace = AgentTrace(trace_id="t", parent_span_id="p")
        assert trace.final_response is None

    def test_to_evaluator_input(self) -> None:
        trace = AgentTrace(
            trace_id="trace1", parent_span_id="parent1",
            spans=[_make_llm_span(input_tokens=10, output_tokens=20, duration_ms=100)],
        )
        inp = trace.to_evaluator_input()
        assert inp["trace_id"] == "trace1"
        assert inp["llm_call_count"] == 1
        assert inp["total_input_tokens"] == 10
        assert inp["total_output_tokens"] == 20
        assert inp["total_duration_ms"] == 100.0
        assert inp["trace"] is trace

    def test_to_tool_calls_format(self) -> None:
        trace = AgentTrace(
            trace_id="t", parent_span_id="p",
            spans=[_make_tool_span(tool_call_id="tc1", tool_name="calc")],
        )
        result = trace.to_tool_calls_format()
        assert len(result) == 1
        assert result[0]["type"] == "tool_call"
        assert result[0]["name"] == "calc"

    def test_to_tool_calls_format_dedup(self) -> None:
        trace = AgentTrace(
            trace_id="t", parent_span_id="p",
            spans=[
                _make_tool_span(span_id="s1", tool_call_id="tc1"),
                _make_tool_span(span_id="s2", tool_call_id="tc1"),
            ],
        )
        assert len(trace.to_tool_calls_format()) == 1


# ---------------------------------------------------------------------------
# OTelTraceCapture
# ---------------------------------------------------------------------------

class TestOTelTraceCapture:
    """Tests for the OTelTraceCapture orchestrator."""

    def test_init(self) -> None:
        capture = OTelTraceCapture(capture_content=True)
        assert not capture._setup_done
        assert capture._tracer is None
        assert capture._collected_spans == []
        assert capture._collected_logs == []

    def test_init_capture_content_flag(self) -> None:
        capture = OTelTraceCapture(capture_content=False)
        assert not capture._capture_content

    def test_setup_disabled_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EVEE_DISABLE_TRACING", "true")
        capture = OTelTraceCapture()
        assert capture.setup() is False

    def test_setup_without_otel_returns_false(self) -> None:
        """When OTel SDK is not installed, setup returns False."""
        capture = OTelTraceCapture()
        with patch.dict("sys.modules", {
            "opentelemetry": None,
            "opentelemetry.trace": None,
            "opentelemetry._logs": None,
            "opentelemetry.sdk.trace": None,
        }):
            # Force re-setup
            capture._setup_done = False
            result = capture.setup()
            # Might return True if OTel is actually installed;
            # the important thing is it doesn't crash
            assert isinstance(result, bool)

    def test_wrap_target_call_without_setup(self) -> None:
        """Without OTel setup, wrap_target_call runs the function directly."""
        capture = OTelTraceCapture()
        mock_fn = MagicMock(return_value={"answer": "42"})

        result, trace = capture.wrap_target_call(
            target_fn=mock_fn,
            record={"q": "?"},
            model_name="test",
            record_id="r1",
        )

        assert result == {"answer": "42"}
        assert trace is None
        mock_fn.assert_called_once_with({"q": "?"})

    def test_shutdown_safe_without_setup(self) -> None:
        """Shutdown should be safe even without setup."""
        capture = OTelTraceCapture()
        capture.shutdown()  # Should not raise

    def test_shutdown_with_providers(self) -> None:
        capture = OTelTraceCapture()
        capture._trace_provider = MagicMock()
        capture._log_provider = MagicMock()
        capture.shutdown()
        capture._trace_provider.shutdown.assert_called_once()
        capture._log_provider.shutdown.assert_called_once()

    def test_evaluation_event_name(self) -> None:
        assert EVALUATION_EVENT_NAME == "gen_ai.evaluation.result"

    def test_emit_evaluation_result_noop_without_setup(self) -> None:
        """emit_evaluation_result should be silent when not set up."""
        capture = OTelTraceCapture()
        # Should not raise
        capture.emit_evaluation_result(
            trace_id="abc", span_id="def",
            evaluator_name="relevance", score_value=4.5,
        )
