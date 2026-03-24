"""Local agent evaluation target using Microsoft Agent Framework (MAF).

Demonstrates the simplified agent target pattern: the user writes normal
MAF agent code and returns just {"answer": text}. The engine's OTel tracing
auto-captures all LLM calls, tool invocations, and messages — evaluators
get the full structured data without the user manually building it.

Install: pip install agent-framework --pre
"""
from __future__ import annotations

import asyncio
import threading
from typing import Annotated, Any, Dict

from pydantic import Field

from azure.ai.evaluation._engine.decorators import target, BaseTarget


# --- Persistent event loop on a background thread ---
# MAF agents are async. The eval engine calls infer() from ThreadPoolExecutor
# workers, which may or may not have an event loop. A dedicated background
# loop avoids all conflicts.
_loop = asyncio.new_event_loop()
_thread = threading.Thread(target=_loop.run_forever, daemon=True)
_thread.start()


def _run_async(coro):
    """Run a coroutine on the persistent background loop and wait for result."""
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=120)


# --- Tool implementations ---

def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    weather = {
        "Paris": "partly cloudy, 18°C, humidity 65%",
        "Tokyo": "rainy, 22°C, humidity 80%",
        "London": "overcast, 14°C, humidity 75%",
        "New York": "sunny, 20°C, humidity 45%",
        "Berlin": "rainy, 12°C, humidity 82%",
        "San Francisco": "foggy, 16°C, humidity 70%",
    }
    return weather.get(location, f"unknown conditions in {location}")


def bring_umbrella(
    weather_condition: Annotated[str, Field(description="The current weather condition, e.g. rainy, sunny.")],
) -> str:
    """Decide whether to bring an umbrella based on the weather condition."""
    rainy = {"rainy", "rain", "thunderstorm", "drizzle", "overcast"}
    should = weather_condition.lower().strip() in rainy
    return f"{'Yes, bring an umbrella' if should else 'No umbrella needed'} — the weather is {weather_condition}."


@target(name="weather_agent_local")
class WeatherAgentLocalTarget(BaseTarget):
    """Evaluates a MAF agent with function tools, executed locally.

    The Microsoft Agent Framework handles the tool execution loop automatically:
    1. Agent receives the query
    2. Agent calls get_weather → framework executes → feeds result back
    3. Agent calls bring_umbrella → framework executes → feeds result back
    4. Agent synthesizes final text answer
    """

    PROJECT_ENDPOINT = "https://foundry-evee-ko9z2s7c.services.ai.azure.com/api/projects/foundry-project-evee-ko9z2s7c"
    DEPLOYMENT = "gpt-4.1-mini"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        from azure.identity import AzureCliCredential
        from agent_framework.azure import AzureOpenAIResponsesClient

        self._tools = [get_weather, bring_umbrella]

        client = AzureOpenAIResponsesClient(
            project_endpoint=self.PROJECT_ENDPOINT,
            deployment_name=self.DEPLOYMENT,
            credential=AzureCliCredential(),
        )
        self._agent = client.as_agent(
            name="WeatherAgent123",
            instructions=(
                "You are a helpful weather assistant. "
                "Use the get_weather tool to check conditions, then the bring_umbrella tool "
                "to advise on umbrella needs. Be concise and practical."
            ),
            tools=self._tools,
        )

    def infer(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Run the MAF agent and return the answer with structured data."""
        query = input.get("query") or input.get("question") or input.get("prompt") or str(list(input.values())[0])

        result = _run_async(self._agent.run(query))

        return {
            "answer": result.text or "",
            "output_items": [msg.to_dict() for msg in result.messages],
            "tool_definitions": self._tools,  # Engine normalizes automatically
        }
