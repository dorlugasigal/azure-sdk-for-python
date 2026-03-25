"""OpenTelemetry trace capture for agent targets.

Transparently instruments OpenAI SDK calls made by agent targets,
capturing full trace data (LLM calls, tool invocations, messages)
that can be used by evaluators and correlated in Azure Monitor.

Auto-enabled when OTel SDK packages are installed:
    pip install opentelemetry-sdk opentelemetry-instrumentation-openai-v2

No configuration needed — the engine detects OTel availability at startup
and captures traces transparently. Disable via environment variable:
    EVEE_DISABLE_TRACING=true
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# OTel evaluation event name per semconv
EVALUATION_EVENT_NAME = "gen_ai.evaluation.result"


@dataclass
class CapturedSpan:
    """A captured OTel span from an agent's execution."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    attributes: Dict[str, Any]
    duration_ms: float
    events: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def operation_name(self) -> Optional[str]:
        return self.attributes.get("gen_ai.operation.name")

    @property
    def model(self) -> Optional[str]:
        return self.attributes.get("gen_ai.response.model") or self.attributes.get("gen_ai.request.model")

    @property
    def input_tokens(self) -> Optional[int]:
        return self.attributes.get("gen_ai.usage.input_tokens")

    @property
    def output_tokens(self) -> Optional[int]:
        return self.attributes.get("gen_ai.usage.output_tokens")

    @property
    def finish_reasons(self) -> Optional[Tuple[str, ...]]:
        return self.attributes.get("gen_ai.response.finish_reasons")


@dataclass
class CapturedLogEvent:
    """A captured OTel log event (input/output messages, tool calls)."""

    trace_id: str
    span_id: str
    body: Any
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTrace:
    """Complete trace of an agent invocation, reconstructed from OTel data.

    This is what evaluators receive — the full picture of what the agent did.
    """

    trace_id: str
    parent_span_id: str
    spans: List[CapturedSpan] = field(default_factory=list)
    log_events: List[CapturedLogEvent] = field(default_factory=list)

    @property
    def llm_calls(self) -> List[CapturedSpan]:
        """Get all LLM inference spans."""
        return [s for s in self.spans if s.operation_name in ("chat", "text_completion", "generate_content")]

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens or 0 for s in self.llm_calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens or 0 for s in self.llm_calls)

    @property
    def total_duration_ms(self) -> float:
        return sum(s.duration_ms for s in self.llm_calls)

    @property
    def tool_calls(self) -> List[Dict[str, Any]]:
        """Extract tool calls from spans and log events."""
        tools = []
        seen_ids: set = set()

        # From spans (MAF/Azure tracer — execute_tool spans + output.messages on chat spans)
        for span in self.spans:
            if span.operation_name == "execute_tool":
                tc_id = span.attributes.get("gen_ai.tool.call.id", "")
                result_raw = span.attributes.get("gen_ai.tool.call.result")

                # Azure tracer puts tool_call_id inside the result JSON
                if not tc_id and result_raw:
                    try:
                        parsed = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
                        if isinstance(parsed, dict):
                            tc_id = parsed.get("tool_call_id", "")
                    except (json.JSONDecodeError, ValueError):
                        pass

                if tc_id and tc_id not in seen_ids:
                    seen_ids.add(tc_id)
                    args = span.attributes.get("gen_ai.tool.call.arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, ValueError):
                            pass
                    tools.append({
                        "id": tc_id,
                        "name": span.attributes.get("gen_ai.tool.name", ""),
                        "arguments": args,
                        "result": result_raw,
                        "span_id": span.span_id,
                    })

            # Also check output.messages for tool_call parts
            out_msgs = span.attributes.get("gen_ai.output.messages")
            if out_msgs:
                msgs = json.loads(out_msgs) if isinstance(out_msgs, str) else out_msgs
                if isinstance(msgs, list):
                    for msg in msgs:
                        if not isinstance(msg, dict):
                            continue
                        for part in msg.get("parts", []):
                            if isinstance(part, dict) and part.get("type") == "tool_call":
                                tc_id = part.get("id", "")
                                if tc_id and tc_id not in seen_ids:
                                    seen_ids.add(tc_id)
                                    tools.append({
                                        "id": tc_id,
                                        "name": part.get("name", ""),
                                        "arguments": part.get("arguments", {}),
                                        "span_id": span.span_id,
                                    })

        # From log events (OpenAI instrumentor format)
        for evt in self.log_events:
            body = evt.body if isinstance(evt.body, dict) else {}
            if "message" in body and isinstance(body.get("message"), dict):
                msg = body["message"]
                for tc in msg.get("tool_calls", []):
                    tc_id = tc.get("id", "")
                    if tc_id and tc_id not in seen_ids:
                        seen_ids.add(tc_id)
                        tools.append({
                            "id": tc_id,
                            "name": tc.get("function", {}).get("name"),
                            "arguments": tc.get("function", {}).get("arguments"),
                            "span_id": evt.span_id,
                        })
            elif "tool_calls" in body:
                for tc in body["tool_calls"]:
                    tc_id = tc.get("id", "")
                    if tc_id and tc_id not in seen_ids:
                        seen_ids.add(tc_id)
                        tools.append({
                            "id": tc_id,
                            "name": tc.get("function", {}).get("name"),
                            "arguments": tc.get("function", {}).get("arguments"),
                            "span_id": evt.span_id,
                        })
        return tools

    @property
    def input_messages(self) -> List[Dict[str, Any]]:
        """Extract user/system input messages from log events."""
        messages = []
        for evt in self.log_events:
            body = evt.body if isinstance(evt.body, dict) else {}
            if "content" in body and "message" not in body and "tool_calls" not in body:
                messages.append(body)
        return messages

    @property
    def final_response(self) -> Optional[str]:
        """Get the final text response from the agent."""
        for evt in reversed(self.log_events):
            body = evt.body if isinstance(evt.body, dict) else {}
            msg = body.get("message", {})
            if isinstance(msg, dict) and msg.get("content") and msg.get("role") == "assistant":
                return msg["content"]
        return None

    def to_evaluator_input(self) -> Dict[str, Any]:
        """Convert trace to a dict suitable for evaluator consumption.

        Returns a dict with:
        - Standard evaluator fields: response (conversation format), tool_calls
        - Trace metadata: token counts, call counts, timing
        - Raw trace object for custom evaluators
        """
        return {
            "trace": self,
            "trace_id": self.trace_id,
            "response": self.to_conversation_format(),
            "tool_calls": self.to_tool_calls_format(),
            "llm_call_count": len(self.llm_calls),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_duration_ms": self.total_duration_ms,
            "final_response": self.final_response,
        }

    def to_conversation_format(self) -> List[Dict[str, Any]]:
        """Convert trace to the conversation message format expected by SDK evaluators.

        Builds from span attributes (MAF) or log events (OpenAI instrumentor).
        """
        messages: List[Dict[str, Any]] = []
        seen_tc_ids: set = set()
        seen_result_ids: set = set()

        # Try span attributes first (MAF emits gen_ai.output.messages here)
        for span in self.spans:
            # Tool results from execute_tool spans
            if span.operation_name == "execute_tool":
                tc_id = span.attributes.get("gen_ai.tool.call.id", "")
                result = span.attributes.get("gen_ai.tool.call.result", "")

                # Azure tracer puts tool_call_id inside the result JSON
                if not tc_id and result:
                    try:
                        parsed = json.loads(result) if isinstance(result, str) else result
                        if isinstance(parsed, dict):
                            tc_id = parsed.get("tool_call_id", "")
                            result = parsed.get("content", result)
                    except (json.JSONDecodeError, ValueError):
                        pass

                if tc_id and tc_id not in seen_result_ids:
                    seen_result_ids.add(tc_id)
                    messages.append({"role": "tool", "tool_call_id": tc_id,
                                     "content": [{"type": "tool_result", "tool_call_id": tc_id, "tool_result": str(result)}]})
                continue

            # Skip invoke_agent spans — they duplicate child span data
            if span.operation_name in ("invoke_agent", "invoke_workflow"):
                continue

            # Process gen_ai.input.messages for tool results
            # (ResponsesInstrumentor puts tool_call_response in the input of the follow-up span)
            inp_raw = span.attributes.get("gen_ai.input.messages")
            if inp_raw:
                inp_msgs = json.loads(inp_raw) if isinstance(inp_raw, str) else inp_raw
                if isinstance(inp_msgs, list):
                    for msg in inp_msgs:
                        if not isinstance(msg, dict) or msg.get("role") != "tool":
                            continue
                        for part in msg.get("parts", []):
                            if not isinstance(part, dict):
                                continue
                            ptype = part.get("type", "")
                            if ptype in ("tool_call_response", "tool_result"):
                                tc_id = part.get("id", "")
                                result_val = part.get("result", part.get("response", part.get("tool_result", "")))
                                if tc_id and tc_id not in seen_result_ids:
                                    seen_result_ids.add(tc_id)
                                    messages.append({"role": "tool", "tool_call_id": tc_id,
                                                     "content": [{"type": "tool_result", "tool_call_id": tc_id, "tool_result": str(result_val)}]})

            out_raw = span.attributes.get("gen_ai.output.messages")
            if not out_raw:
                continue
            out_msgs = json.loads(out_raw) if isinstance(out_raw, str) else out_raw
            if not isinstance(out_msgs, list):
                continue
            for msg in out_msgs:
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role", "assistant")
                items = []
                for part in msg.get("parts", []):
                    if not isinstance(part, dict):
                        continue
                    ptype = part.get("type", "")
                    if ptype == "tool_call":
                        tc_id = part.get("id", "")
                        if tc_id and tc_id not in seen_tc_ids:
                            seen_tc_ids.add(tc_id)
                            args = part.get("arguments", {})
                            if isinstance(args, str):
                                try: args = json.loads(args)
                                except: pass
                            items.append({"type": "tool_call", "tool_call_id": tc_id, "name": part.get("name", ""), "arguments": args})
                    elif ptype == "text":
                        text = part.get("content", part.get("text", ""))
                        if text:
                            items.append({"type": "text", "text": text})
                if items:
                    messages.append({"role": role, "content": items})

        if messages:
            return self._sort_conversation(messages)

        # Fall back to log events (OpenAI instrumentor format)
        for evt in self.log_events:
            body = evt.body if isinstance(evt.body, dict) else {}
            if "message" in body and isinstance(body.get("message"), dict):
                msg = body["message"]
                role = msg.get("role", "assistant")
                if msg.get("tool_calls"):
                    items = []
                    for tc in msg["tool_calls"]:
                        tc_id = tc.get("id", "")
                        if tc_id and tc_id not in seen_tc_ids:
                            seen_tc_ids.add(tc_id)
                            func = tc.get("function", {})
                            args = func.get("arguments", {})
                            if isinstance(args, str):
                                try: args = json.loads(args)
                                except: pass
                            items.append({"type": "tool_call", "tool_call_id": tc_id, "name": func.get("name", ""), "arguments": args})
                    if items:
                        messages.append({"role": role, "content": items})
                elif msg.get("content"):
                    messages.append({"role": role, "content": [{"type": "text", "text": msg["content"]}]})
            elif "content" in body and "id" in body and "message" not in body:
                rid = body["id"]
                if rid not in seen_result_ids:
                    seen_result_ids.add(rid)
                    messages.append({"role": "tool", "tool_call_id": rid,
                                     "content": [{"type": "tool_result", "tool_call_id": rid, "tool_result": body["content"]}]})
            elif "index" in body and "finish_reason" in body:
                msg = body.get("message", {})
                if isinstance(msg, dict) and msg.get("content"):
                    messages.append({"role": msg.get("role", "assistant"), "content": [{"type": "text", "text": msg["content"]}]})

        return messages

    def _sort_conversation(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort messages so tool results follow their corresponding tool calls."""
        tc_msgs, result_map, text_msgs = [], {}, []
        for msg in messages:
            if msg["role"] == "tool":
                result_map[msg.get("tool_call_id", "")] = msg
            elif msg["role"] == "assistant":
                has_tc = any(isinstance(c, dict) and c.get("type") == "tool_call" for c in msg.get("content", []))
                if has_tc:
                    tc_msgs.append(msg)
                else:
                    text_msgs.append(msg)
        sorted_msgs = []
        for tc_msg in tc_msgs:
            sorted_msgs.append(tc_msg)
            for c in tc_msg.get("content", []):
                if isinstance(c, dict) and c.get("type") == "tool_call":
                    tc_id = c.get("tool_call_id", "")
                    if tc_id in result_map:
                        sorted_msgs.append(result_map.pop(tc_id))
        sorted_msgs.extend(result_map.values())
        sorted_msgs.extend(text_msgs)
        return sorted_msgs

    def to_tool_calls_format(self) -> List[Dict[str, Any]]:
        """Convert trace tool calls to the format expected by ToolCallAccuracyEvaluator."""
        result = []
        seen_ids: set = set()
        for tc in self.tool_calls:
            tc_id = tc.get("id", "")
            if tc_id in seen_ids:
                continue
            seen_ids.add(tc_id)
            args = tc.get("arguments", {})
            if isinstance(args, str):
                try: args = json.loads(args)
                except: pass
            result.append({"type": "tool_call", "tool_call_id": tc_id, "name": tc.get("name", ""), "arguments": args})
        return result


class OTelTraceCapture:
    """Captures OTel traces from agent target invocations.

    Sets up OTel TracerProvider + LoggerProvider with in-memory collectors,
    auto-instruments the OpenAI SDK, and provides methods to wrap target
    invocations in parent spans and collect the resulting traces.
    """

    def __init__(self, capture_content: bool = True) -> None:
        self._capture_content = capture_content
        self._setup_done = False
        self._tracer = None

        # In-memory collectors
        self._span_lock = Lock()
        self._log_lock = Lock()
        self._collected_spans: List[Any] = []
        self._collected_logs: List[Any] = []

        # OTel providers (created during setup)
        self._trace_provider = None
        self._log_provider = None

    def setup(self) -> bool:
        """Set up OTel instrumentation. Returns True if successful.

        Auto-detects OTel SDK availability. Disable with EVEE_DISABLE_TRACING=true.
        Safe to call multiple times — only sets up once.
        """
        if self._setup_done:
            return True

        import os
        if os.environ.get("EVEE_DISABLE_TRACING", "").lower() in ("true", "1", "yes"):
            logger.debug("OTel trace capture disabled via EVEE_DISABLE_TRACING")
            return False

        try:
            from opentelemetry import trace as otel_trace, _logs as otel_logs
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import (
                SimpleSpanProcessor,
                SpanExporter,
                SpanExportResult,
            )
            from opentelemetry.sdk._logs import LoggerProvider
            from opentelemetry.sdk._logs.export import (
                SimpleLogRecordProcessor,
                LogExporter,
                LogExportResult,
            )
        except ImportError:
            logger.debug("OpenTelemetry SDK not available — trace capture disabled")
            return False

        # Create span collector
        capture = self

        class _SpanCollector(SpanExporter):
            def export(self, spans):
                with capture._span_lock:
                    capture._collected_spans.extend(spans)
                return SpanExportResult.SUCCESS

            def shutdown(self):
                pass

        class _LogCollector(LogExporter):
            def export(self, logs):
                with capture._log_lock:
                    capture._collected_logs.extend(logs)
                return LogExportResult.SUCCESS

            def shutdown(self):
                pass

        # Set up providers
        self._trace_provider = TracerProvider()
        self._trace_provider.add_span_processor(SimpleSpanProcessor(_SpanCollector()))
        otel_trace.set_tracer_provider(self._trace_provider)

        self._log_provider = LoggerProvider()
        self._log_provider.add_log_record_processor(SimpleLogRecordProcessor(_LogCollector()))
        otel_logs.set_logger_provider(self._log_provider)

        # Auto-instrument OpenAI SDK (chat.completions.create)
        try:
            from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
            OpenAIInstrumentor().instrument()
            logger.info("OTel trace capture: OpenAI auto-instrumentation activated")
        except ImportError:
            logger.debug("opentelemetry-instrumentation-openai-v2 not installed — "
                         "only manual spans will be captured")

        # Instrument OpenAI Responses API (responses.create)
        # azure-ai-projects has a ResponsesInstrumentor that patches the Responses API
        try:
            from azure.ai.projects.telemetry._responses_instrumentor import ResponsesInstrumentor
            ResponsesInstrumentor().instrument(enable_content_recording=True)
            logger.info("OTel trace capture: OpenAI Responses API instrumentation activated")
        except ImportError:
            pass  # azure-ai-projects not installed

        # Enable MAF (Microsoft Agent Framework) instrumentation if available
        # MAF emits full OTel traces (spans, messages, tool calls, tool definitions)
        # to the global providers — which we just set up above.
        try:
            from agent_framework.observability import enable_instrumentation
            enable_instrumentation(enable_sensitive_data=True)
            logger.info("OTel trace capture: MAF instrumentation enabled")
        except ImportError:
            pass  # MAF not installed

        # Enable LangChain Azure AI OTel tracer if available
        # This callback emits full GenAI semconv spans including gen_ai.tool.definitions,
        # execute_tool spans with arguments/results, and invoke_agent spans.
        # It's attached as a callback to LangChain runs automatically.
        self._langchain_tracer = None
        try:
            from langchain_azure_ai.callbacks.tracers import AzureAIOpenTelemetryTracer
            self._langchain_tracer = AzureAIOpenTelemetryTracer()
            logger.info("OTel trace capture: LangChain Azure AI tracer available")
        except ImportError:
            pass  # langchain-azure-ai not installed

        # Content capture env vars
        if self._capture_content:
            import os
            os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
            os.environ.setdefault("AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING", "true")
            os.environ.setdefault("AZURE_SDK_TRACING_IMPLEMENTATION", "opentelemetry")

        self._tracer = otel_trace.get_tracer("azure.ai.evaluation.engine")
        self._setup_done = True
        return True

    def wrap_target_call(
        self,
        target_fn: Callable,
        record: Dict[str, Any],
        model_name: str,
        record_id: str,
    ) -> Tuple[Any, Optional[AgentTrace]]:
        """Wrap a target invocation in a parent OTel span and collect traces.

        Args:
            target_fn: The target's infer method (e.g., model.infer)
            record: The input record being evaluated
            model_name: Name of the target/model variant
            record_id: Unique ID for this record

        Returns:
            Tuple of (inference_output, agent_trace).
            agent_trace is None if OTel setup failed.
        """
        if not self._setup_done or self._tracer is None:
            # OTel not available — run without tracing
            return target_fn(record), None

        from opentelemetry import trace as otel_trace

        # Clear collectors for this invocation
        with self._span_lock:
            self._collected_spans.clear()
        with self._log_lock:
            self._collected_logs.clear()

        # Run target within a parent span
        with self._tracer.start_as_current_span(
            "evee.target.invoke",
            attributes={
                "evee.target.name": model_name,
                "evee.record.id": record_id,
            },
        ) as parent_span:
            parent_ctx = parent_span.get_span_context()
            trace_id = format(parent_ctx.trace_id, "032x")
            parent_span_id = format(parent_ctx.span_id, "016x")

            # Execute the target — all OpenAI calls inside will be traced
            result = target_fn(record)

        # Collect and structure the trace
        agent_trace = self._build_trace(trace_id, parent_span_id)
        return result, agent_trace

    def emit_evaluation_result(
        self,
        trace_id: str,
        span_id: str,
        evaluator_name: str,
        score_value: Optional[float] = None,
        score_label: Optional[str] = None,
        explanation: Optional[str] = None,
    ) -> None:
        """Emit a gen_ai.evaluation.result OTel event.

        This attaches evaluation scores to the agent's trace, so they appear
        in Azure Monitor / App Insights alongside the agent's execution data.
        """
        if not self._setup_done:
            return

        try:
            from opentelemetry._events import get_event_logger, Event

            event_logger = get_event_logger(
                "azure.ai.evaluation.engine",
            )

            attributes: Dict[str, Any] = {
                "gen_ai.evaluation.name": evaluator_name,
            }
            if score_value is not None:
                attributes["gen_ai.evaluation.score.value"] = float(score_value)
            if score_label:
                attributes["gen_ai.evaluation.score.label"] = score_label
            if explanation:
                attributes["gen_ai.evaluation.explanation"] = explanation

            # Convert trace_id/span_id back to ints for OTel
            tid = int(trace_id, 16) if trace_id else None
            sid = int(span_id, 16) if span_id else None

            event_logger.emit(
                Event(
                    name=EVALUATION_EVENT_NAME,
                    attributes=attributes,
                    body=EVALUATION_EVENT_NAME,
                    trace_id=tid,
                    span_id=sid,
                )
            )
        except Exception:
            pass  # Evaluation result emission should never break evaluation

    def shutdown(self) -> None:
        """Clean up OTel providers."""
        if self._trace_provider:
            try:
                self._trace_provider.shutdown()
            except Exception:
                pass
        if self._log_provider:
            try:
                self._log_provider.shutdown()
            except Exception:
                pass

    def _build_trace(self, trace_id: str, parent_span_id: str) -> AgentTrace:
        """Build an AgentTrace from collected spans and log events."""
        trace = AgentTrace(trace_id=trace_id, parent_span_id=parent_span_id)

        # Process spans
        with self._span_lock:
            for span in self._collected_spans:
                span_trace_id = format(span.context.trace_id, "032x")
                if span_trace_id != trace_id:
                    continue  # Skip spans from other traces

                span_id = format(span.context.span_id, "016x")
                p_span_id = (
                    format(span.parent.span_id, "016x") if span.parent else None
                )

                # Skip the parent "evee.target.invoke" span itself
                if span.name == "evee.target.invoke":
                    continue

                captured = CapturedSpan(
                    name=span.name,
                    trace_id=span_trace_id,
                    span_id=span_id,
                    parent_span_id=p_span_id,
                    attributes=dict(span.attributes or {}),
                    duration_ms=(span.end_time - span.start_time) / 1e6,
                )
                trace.spans.append(captured)

        # Process log events
        with self._log_lock:
            for log in self._collected_logs:
                lr = getattr(log, "log_record", log)
                log_trace_id = (
                    format(lr.trace_id, "032x") if lr.trace_id else None
                )
                if log_trace_id != trace_id:
                    continue

                log_span_id = (
                    format(lr.span_id, "016x") if lr.span_id else None
                )
                body = getattr(lr, "body", None)
                attrs = dict(getattr(lr, "attributes", {}) or {})

                captured_log = CapturedLogEvent(
                    trace_id=log_trace_id,
                    span_id=log_span_id,
                    body=body,
                    attributes=attrs,
                )
                trace.log_events.append(captured_log)

        return trace
