"""Custom agent evaluation metrics — auto-discovered via @evaluator decorator.

Demonstrates custom metrics for agent evaluation that work both locally and on
Foundry cloud (sandbox-compatible: only built-in Python + sandbox packages).
"""
import json
import re

from azure.ai.evaluation._engine.decorators import evaluator, BaseEvaluator


# --- Helper functions (module-level so @evaluator wrapper doesn't interfere) ---

# Patterns that indicate a non-answer or cop-out
_HEDGING_PATTERNS = [
    re.compile(r"(?i)^i('m| am) (not able|unable|sorry)"),
    re.compile(r"(?i)^(unfortunately|i can('| )not|i don('| )t have access)"),
    re.compile(r"(?i)^(as an ai|i('m| am) (just )?an? (ai|language model|assistant))"),
    re.compile(r"(?i)(i('m| am) not sure|i don('| )t know)"),
    re.compile(r"(?i)^(error|failed|exception|traceback)"),
    re.compile(r"(?i)please (try again|contact|reach out)"),
]

_STOP_WORDS = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all",
    "can", "had", "her", "was", "one", "our", "out", "has",
    "how", "what", "who", "why", "when", "where", "which",
    "that", "this", "with", "from", "have", "will", "does",
})


def _extract_from_items(items):
    """Extract text content and tool call count from output_items list."""
    text_parts = []
    tool_calls = 0

    for item in items:
        if not isinstance(item, dict):
            text_parts.append(str(item))
            continue

        item_type = item.get("type", "")
        if item_type in ("message", "text"):
            content = item.get("text", "") or item.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        text_parts.append(part.get("text", ""))
                    else:
                        text_parts.append(str(part))
            elif content:
                text_parts.append(str(content))
        elif item_type == "function_call":
            tool_calls += 1
        elif item_type == "function_call_output":
            pass  # Tool result — don't count as user-facing text
        else:
            for key in ("text", "content", "output"):
                val = item.get(key)
                if val and isinstance(val, str):
                    text_parts.append(val)
                    break

    return " ".join(text_parts), tool_calls, True


def _parse_response(response):
    """Parse response into text content and tool call count.

    Handles plain text strings, lists, and JSON-serialized output_items.
    Returns (text, tool_call_count, has_structured_output).
    """
    if not response:
        return "", 0, False

    if isinstance(response, list):
        return _extract_from_items(response)

    if isinstance(response, str):
        stripped = response.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return _extract_from_items(parsed)
                if isinstance(parsed, dict):
                    return _extract_from_items([parsed])
            except (json.JSONDecodeError, ValueError):
                pass
        return response, 0, False

    return str(response), 0, False


# --- The metric ---

@evaluator(name="response_completeness")
class ResponseCompletenessMetric(BaseEvaluator):
    """Scores whether an agent produced a complete, substantive answer.

    Agents often make tool calls but fail to synthesize a final answer, or
    produce hedging/refusal responses. This metric catches those cases using
    rule-based heuristics — complementing LLM-based evaluators like coherence.

    Works with both text responses (model.response) and structured output
    (model.output_items). Sandbox-compatible for Foundry cloud evaluation.
    """

    def compute(self, response: str = "", query: str = "", **kwargs):
        """Evaluate response completeness.

        Args:
            response: Agent's text response (model.response) or structured
                output (model.output_items as JSON string).
            query: The original user query (dataset.query).
        """
        text, tool_calls, has_structured = _parse_response(response)

        scores = {}

        # 1. Presence — is there any substantive text?
        text_length = len(text.strip())
        if text_length == 0:
            scores["presence"] = 0.0
        elif text_length < 20:
            scores["presence"] = 0.3
        elif text_length < 50:
            scores["presence"] = 0.6
        else:
            scores["presence"] = 1.0

        # 2. Directness — does the response dodge the question?
        hedging_detected = any(p.search(text) for p in _HEDGING_PATTERNS)
        scores["directness"] = 0.2 if hedging_detected else 1.0

        # 3. Query coverage — does the response address key terms from the query?
        if query.strip():
            query_terms = set(re.findall(r"\b[a-zA-Z]{3,}\b", query.lower()))
            response_terms = set(re.findall(r"\b[a-zA-Z]{3,}\b", text.lower()))
            query_terms -= _STOP_WORDS
            if query_terms:
                overlap = len(query_terms & response_terms) / len(query_terms)
                scores["coverage"] = round(min(overlap * 1.5, 1.0), 3)
            else:
                scores["coverage"] = 1.0
        else:
            scores["coverage"] = 1.0

        # 4. Synthesis — if tools were used, was there a final text synthesis?
        if has_structured and tool_calls > 0:
            if text_length > 50:
                scores["synthesis"] = 1.0
            elif text_length > 20:
                scores["synthesis"] = 0.5
            else:
                scores["synthesis"] = 0.1  # Tool calls without synthesis
        else:
            scores["synthesis"] = 1.0  # No tools → synthesis N/A (full score)

        # Weighted composite
        overall = (
            scores["presence"] * 0.30
            + scores["directness"] * 0.25
            + scores["coverage"] * 0.25
            + scores["synthesis"] * 0.20
        )

        return {
            "completeness_score": round(overall, 3),
            "completeness_presence": scores["presence"],
            "completeness_directness": scores["directness"],
            "completeness_coverage": scores["coverage"],
            "completeness_synthesis": scores["synthesis"],
            "completeness_tool_calls": tool_calls,
            "completeness_response_length": text_length,
        }

    def aggregate(self, scores):
        vals = [s["completeness_score"] for s in scores]
        tool_counts = [s["completeness_tool_calls"] for s in scores]
        lengths = [s["completeness_response_length"] for s in scores]
        return {
            "completeness_score_mean": round(sum(vals) / len(vals), 3),
            "completeness_score_min": round(min(vals), 3),
            "completeness_tool_calls_mean": round(sum(tool_counts) / len(tool_counts), 1),
            "completeness_response_length_mean": round(sum(lengths) / len(lengths), 1),
        }
