"""LangChain agent evaluation target.

Demonstrates the simplified agent target pattern: the user writes normal
LangChain agent code and returns just {"answer": text}. The engine's OTel
tracing auto-captures all tool calls, messages, and token usage — evaluators
get the full structured data without the user manually building it.

Install: pip install langchain langchain-openai azure-identity
"""
from __future__ import annotations

from typing import Any, Dict

from azure.ai.evaluation._engine.decorators import target, BaseTarget


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
    """Decide whether to bring an umbrella based on the weather condition."""
    rainy = {"rainy", "rain", "thunderstorm", "drizzle", "overcast"}
    should = weather_condition.lower().strip() in rainy
    return f"{'Yes, bring an umbrella' if should else 'No umbrella needed'} — {weather_condition}."


AZURE_ENDPOINT = "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/"


@target(name="weather_agent_langchain")
class WeatherAgentLangChainTarget(BaseTarget):
    """LangChain agent with tools for weather queries.

    The user writes normal LangChain code — the engine auto-captures
    all LLM calls and tool invocations via OTel tracing.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        from langchain_openai import AzureChatOpenAI
        from langchain_core.tools import tool as langchain_tool
        from azure.identity import AzureCliCredential, get_bearer_token_provider

        token_provider = get_bearer_token_provider(
            AzureCliCredential(), "https://cognitiveservices.azure.com/.default"
        )

        self._llm = AzureChatOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            azure_deployment="gpt-4.1-mini",
            azure_ad_token_provider=token_provider,
            api_version="2025-04-01-preview",
        )

        @langchain_tool
        def lc_get_weather(location: str) -> str:
            """Get the weather for a given location."""
            return get_weather(location)

        @langchain_tool
        def lc_bring_umbrella(weather_condition: str) -> str:
            """Decide whether to bring an umbrella based on the weather condition."""
            return bring_umbrella(weather_condition)

        self._tools = [lc_get_weather, lc_bring_umbrella]
        self._llm_with_tools = self._llm.bind_tools(self._tools)
        self._tool_map = {t.name: t for t in self._tools}

    def infer(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Run the LangChain agent and return just the answer.

        The engine's OTel tracing automatically captures all LLM calls,
        tool invocations, and messages — no manual tracking needed.
        output_items, tool_calls, and tool_definitions are auto-enriched.
        """
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

        query = input.get("query") or input.get("question") or input.get("prompt") or str(list(input.values())[0])

        messages = [
            SystemMessage(content="You are a helpful weather assistant. Use tools to answer. Be concise."),
            HumanMessage(content=query),
        ]

        # Standard LangChain tool execution loop
        for _ in range(5):
            response = self._llm_with_tools.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                break

            for tc in response.tool_calls:
                tool = self._tool_map.get(tc["name"])
                result = tool.invoke(tc["args"]) if tool else f"Unknown tool: {tc['name']}"
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        else:
            # If loop exhausted, get final response
            response = self._llm_with_tools.invoke(messages)
            messages.append(response)

        # Just return the answer — engine auto-enriches with trace data
        return {"answer": response.content or ""}

