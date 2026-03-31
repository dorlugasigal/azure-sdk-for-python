"""Utilities for extracting tool definitions from OTel agent traces."""
from __future__ import annotations

import json
from typing import Any, Dict, List


def _extract_tool_definitions_from_trace(agent_trace: Any) -> List[Dict[str, Any]]:
    """Extract tool definitions from OTel trace spans.

    Checks multiple sources in priority order:

    1. ``gen_ai.tool.definitions`` (MAF / standard semconv)
    2. ``gen_ai.request.tools`` (azure-ai-projects ResponsesInstrumentor)
    3. Inferred from tool calls in the conversation (fallback, same as RAISvc cloud)

    :param agent_trace: The OTel agent trace object containing spans and tool calls.
    :type agent_trace: Any
    :returns: A list of tool definition dictionaries.
    :rtype: list[dict[str, Any]]
    """
    # Try explicit tool definitions from span attributes
    for attr_name in ("gen_ai.tool.definitions", "gen_ai.request.tools"):
        for span in agent_trace.spans:
            tool_defs = span.attributes.get(attr_name)
            if not tool_defs:
                continue

            if isinstance(tool_defs, str):
                try:
                    parsed = json.loads(tool_defs)
                except (json.JSONDecodeError, ValueError):
                    continue
            elif isinstance(tool_defs, (list, tuple)):
                parsed = list(tool_defs)
            else:
                continue

            # Flatten nested OpenAI format if needed
            result: List[Dict[str, Any]] = []
            for td in parsed:
                if isinstance(td, dict) and "function" in td and isinstance(td["function"], dict):
                    flat: Dict[str, Any] = {"type": td.get("type", "function")}
                    flat.update(td["function"])
                    result.append(flat)
                elif isinstance(td, dict):
                    result.append(td)
            if result:
                return result

    # Fallback: infer tool definitions from tool calls in the trace
    # (same approach as RAISvc cloud evaluation)
    return _infer_tool_definitions_from_trace(agent_trace)


def _infer_tool_definitions_from_trace(agent_trace: Any) -> List[Dict[str, Any]]:
    """Infer tool definitions from tool calls found in the trace.

    When ``gen_ai.tool.definitions`` is not available, we can derive basic tool
    definitions from the tool calls themselves (names + argument types).
    This matches what the RAISvc cloud evaluation does as a fallback.

    :param agent_trace: The OTel agent trace object containing spans and tool calls.
    :type agent_trace: Any
    :returns: A list of inferred tool definition dictionaries.
    :rtype: list[dict[str, Any]]
    """
    inferred: Dict[str, Dict[str, Any]] = {}

    # From execute_tool spans
    for span in agent_trace.spans:
        if span.operation_name == "execute_tool":
            name = span.attributes.get("gen_ai.tool.name", "")
            if name and name not in inferred:
                args_raw = span.attributes.get("gen_ai.tool.call.arguments", {})
                if isinstance(args_raw, str):
                    try:
                        args_raw = json.loads(args_raw)
                    except (json.JSONDecodeError, ValueError):
                        args_raw = {}

                # Build parameter schema from argument values
                props = _build_props_from_args(args_raw)

                inferred[name] = {
                    "name": name,
                    "type": "function",
                    "description": span.attributes.get("gen_ai.tool.description", name),
                    "parameters": {"type": "object", "properties": props},
                }

    # From tool_calls in the trace
    for tc in agent_trace.tool_calls:
        name = tc.get("name", "")
        if name and name not in inferred:
            args = tc.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    args = {}

            props = _build_props_from_args(args)

            inferred[name] = {
                "name": name,
                "type": "function",
                "description": name,
                "parameters": {"type": "object", "properties": props},
            }

    return list(inferred.values())


def _build_props_from_args(args: Any) -> Dict[str, Dict[str, str]]:
    """Build a JSON-Schema properties dict from argument values.

    :param args: A dictionary of argument names to their values.
    :type args: Any
    :returns: A dictionary mapping argument names to their JSON-Schema type descriptors.
    :rtype: dict[str, dict[str, str]]
    """
    props: Dict[str, Dict[str, str]] = {}
    if isinstance(args, dict):
        for k, v in args.items():
            if isinstance(v, str):
                props[k] = {"type": "string"}
            elif isinstance(v, bool):
                props[k] = {"type": "boolean"}
            elif isinstance(v, int):
                props[k] = {"type": "integer"}
            elif isinstance(v, float):
                props[k] = {"type": "number"}
            else:
                props[k] = {"type": "string"}
    return props
