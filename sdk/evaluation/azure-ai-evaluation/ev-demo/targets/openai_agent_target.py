"""OpenAI SDK agent evaluation target.

Demonstrates the simplified agent target pattern: the user writes normal
OpenAI Responses API agent code and returns just {"response": text}. The engine's
OTel tracing auto-captures all LLM calls, tool invocations, and messages.

Install: pip install openai azure-identity azure-ai-projects
"""
from __future__ import annotations

import json
from typing import Any, Dict

from azure.ai.evaluation._engine.decorators import target, BaseTarget
from azure.ai.evaluation._engine.models import ExecutionContext


# Tool implementations
def get_weather(location: str) -> str:
    """Get the weather for a given location."""
    weather = {
        "Paris": "partly cloudy, 18°C, humidity 65%",
        "Tokyo": "rainy, 22°C, humidity 80%",
        "London": "overcast, 14°C, humidity 75%",
        "New York": "sunny, 20°C, humidity 45%",
        "Berlin": "rainy, 12°C, humidity 82%",
    }
    return weather.get(location, f"unknown conditions in {location}")


def bring_umbrella(weather_condition: str) -> str:
    """Decide whether to bring an umbrella."""
    rainy = {"rainy", "rain", "thunderstorm", "drizzle", "overcast"}
    should = weather_condition.lower().strip() in rainy
    return f"{'Yes, bring an umbrella' if should else 'No umbrella needed'} — {weather_condition}."


TOOLS = {"get_weather": get_weather, "bring_umbrella": bring_umbrella}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get the weather for a given location.",
        "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
    },
    {
        "type": "function",
        "name": "bring_umbrella",
        "description": "Decide whether to bring an umbrella based on the weather condition.",
        "parameters": {"type": "object", "properties": {"weather_condition": {"type": "string"}}, "required": ["weather_condition"]},
    },
]


@target(name="weather_agent_openai")
class WeatherAgentOpenAITarget(BaseTarget):
    """OpenAI Responses API agent with manual tool execution loop.

    The user writes normal OpenAI code — the engine auto-captures
    all LLM calls and tool invocations via OTel tracing.
    """

    def __init__(self, context: ExecutionContext = None, connection_name: str = "default", **kwargs: Any) -> None:
        super().__init__(**kwargs)

        conn = context.connections_registry[connection_name]
        self._deployment = getattr(conn, "azure_deployment", "gpt-4.1")

        from azure.identity import AzureCliCredential
        from azure.ai.projects import AIProjectClient

        project_client = AIProjectClient(endpoint=conn.azure_ai_project, credential=AzureCliCredential())
        self._client = project_client.get_openai_client()

    def infer(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Run the OpenAI agent and return just the answer.

        The engine transparently captures tool calls and messages via OTel
        when available.
        """
        query = input.get("query") or input.get("question") or input.get("prompt") or str(list(input.values())[0])

        response = self._client.responses.create(
            model=self._deployment,
            input=query,
            tools=TOOL_SCHEMAS,
            instructions="You are a helpful weather assistant. Use tools to answer. Be concise.",
        )

        # Standard tool execution loop — accumulate all output items
        all_output_items = list(response.output)

        for _ in range(5):
            pending = [item for item in response.output if item.type == "function_call"]
            if not pending:
                break

            tool_results = []
            for tc in pending:
                func = TOOLS.get(tc.name)
                args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                result = func(**args) if func else f"Unknown tool: {tc.name}"
                tool_results.append({
                    "type": "function_call_output",
                    "call_id": tc.call_id,
                    "output": result if isinstance(result, str) else json.dumps(result),
                })

            response = self._client.responses.create(
                model=self._deployment,
                input=tool_results,
                tools=TOOL_SCHEMAS,
                previous_response_id=response.id,
            )
            all_output_items.extend(response.output)

        # Serialize the full conversation — engine extracts tool data from output_items
        output_items = []
        for item in all_output_items:
            if item.type == "message":
                # Serialize content parts (ResponseOutputText objects → dicts)
                content_parts = []
                for part in getattr(item, "content", []):
                    text = getattr(part, "text", str(part)) if not isinstance(part, (str, dict)) else (part if isinstance(part, str) else part.get("text", ""))
                    content_parts.append({"type": "text", "text": text})
                output_items.append({
                    "role": getattr(item, "role", "assistant"),
                    "content": content_parts or [{"type": "text", "text": ""}],
                    "type": "message",
                })
            elif item.type == "function_call":
                output_items.append({
                    "role": "assistant",
                    "content": [{
                        "type": "tool_call",
                        "tool_call_id": getattr(item, "call_id", ""),
                        "name": item.name,
                        "arguments": json.loads(item.arguments) if isinstance(item.arguments, str) else item.arguments,
                    }],
                })
            elif item.type == "function_call_output":
                output_items.append({
                    "role": "tool",
                    "tool_call_id": getattr(item, "call_id", ""),
                    "content": [{"type": "tool_result", "tool_result": getattr(item, "output", "")}],
                })

        return {"response": response.output_text or "", "output_items": output_items}

