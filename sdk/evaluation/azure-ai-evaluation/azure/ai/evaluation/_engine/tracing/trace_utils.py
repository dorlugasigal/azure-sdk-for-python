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

    When the same tool is invoked multiple times with different argument types,
    the parameter schemas are merged to produce union types (e.g.
    ``["string", "integer"]``), aligning with the cloud SDK's
    ``_update_tool_parameters_schema`` behaviour.

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
            if not name:
                continue

            args_raw = span.attributes.get("gen_ai.tool.call.arguments", {})
            if isinstance(args_raw, str):
                try:
                    args_raw = json.loads(args_raw)
                except (json.JSONDecodeError, ValueError):
                    args_raw = {}

            if name in inferred:
                # Merge new argument types into existing schema
                existing_props = inferred[name]["parameters"]["properties"]
                _build_props_from_args(args_raw, existing_props)
            else:
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
        if not name:
            continue

        args = tc.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                args = {}

        if name in inferred:
            existing_props = inferred[name]["parameters"]["properties"]
            _build_props_from_args(args, existing_props)
        else:
            props = _build_props_from_args(args)
            inferred[name] = {
                "name": name,
                "type": "function",
                "description": name,
                "parameters": {"type": "object", "properties": props},
            }

    return list(inferred.values())


def _infer_schema_type(value: Any) -> str:
    """Map a Python value to its JSON Schema type string.

    The ``bool`` check is performed before ``int`` because
    ``isinstance(True, int)`` is ``True`` in Python.

    :param value: The Python value to inspect.
    :type value: Any
    :returns: A JSON Schema type string.
    :rtype: str
    """
    if value is None:
        return "null"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "string"


def _as_type_list(type_value: Any) -> List[str]:
    """Normalise a JSON Schema ``type`` entry to a list of type strings.

    :param type_value: A single type string or a list of type strings.
    :type type_value: Any
    :returns: A list of type strings.
    :rtype: list[str]
    """
    if isinstance(type_value, list):
        return list(type_value)
    if isinstance(type_value, str):
        return [type_value]
    return []


def _merge_schema_types(existing_type: Any, new_type: Any) -> Any:
    """Merge two JSON Schema type declarations, avoiding duplicates.

    If the merged result contains a single type the scalar string form is
    returned; otherwise a list of unique types is returned.

    :param existing_type: The current type value (string or list).
    :type existing_type: Any
    :param new_type: The new type value to merge in (string or list).
    :type new_type: Any
    :returns: A merged type — either a single string or a list of strings.
    :rtype: str | list[str]
    """
    merged: List[str] = _as_type_list(existing_type)
    for t in _as_type_list(new_type):
        if t not in merged:
            merged.append(t)
    return merged[0] if len(merged) == 1 else merged


def _build_props_from_args(
    args: Any,
    existing_props: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Build a JSON-Schema properties dict from argument values.

    When *existing_props* is provided the new argument types are merged into
    it (mutating in place) so that repeated invocations with different types
    produce union types.  This mirrors the cloud SDK's
    ``_update_tool_parameters_schema`` behaviour.

    :param args: A dictionary of argument names to their values.
    :type args: Any
    :param existing_props: An optional existing properties dict to merge into.
    :type existing_props: dict[str, dict[str, Any]] | None
    :returns: A dictionary mapping argument names to their JSON-Schema type descriptors.
    :rtype: dict[str, dict[str, Any]]
    """
    props: Dict[str, Dict[str, Any]] = existing_props if existing_props is not None else {}
    if isinstance(args, dict):
        for k, v in args.items():
            inferred_type = _infer_schema_type(v)
            if k in props:
                props[k]["type"] = _merge_schema_types(props[k].get("type", inferred_type), inferred_type)
            else:
                props[k] = {"type": inferred_type}
    return props
