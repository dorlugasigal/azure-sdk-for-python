"""LangChain agent evaluation target.

Demonstrates the simplified agent target pattern using LangGraph's
create_react_agent — the proper way to build LangChain agents.
The user just returns {"answer": text}, engine handles the rest via OTel.

Install: pip install langchain-openai langgraph azure-identity
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


@target(name="weather_agent_langchain")
class WeatherAgentLangChainTarget(BaseTarget):
    """LangChain agent using create_react_agent — the standard pattern.

    The agent handles the full tool execution loop automatically.
    OTel captures all LLM calls via the OpenAI instrumentor.
    """

    def __init__(self, connections_registry: Dict[str, Any] = None, connection_name: str = "default", **kwargs: Any) -> None:
        super().__init__(**kwargs)

        conn = self.get_connection(connections_registry, connection_name)
        azure_endpoint = conn.get("azure_endpoint")
        if not azure_endpoint:
            raise ValueError(
                f"Connection '{connection_name}' is missing 'azure_endpoint'. "
                "Add it to the connections section of your YAML config."
            )
        deployment = conn.get("azure_deployment", "gpt-4.1")

        from langchain_openai import AzureChatOpenAI
        from langchain_core.tools import tool as langchain_tool
        from langgraph.prebuilt import create_react_agent
        from azure.identity import AzureCliCredential, get_bearer_token_provider

        token_provider = get_bearer_token_provider(
            AzureCliCredential(), "https://cognitiveservices.azure.com/.default"
        )

        model = AzureChatOpenAI(
            azure_endpoint=azure_endpoint,
            azure_deployment=deployment,
            model=deployment,
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

        self._agent = create_react_agent(model, tools=[lc_get_weather, lc_bring_umbrella])

    def infer(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """Run the LangChain agent and return just the answer."""
        query = input.get("query") or input.get("question") or input.get("prompt") or str(list(input.values())[0])

        # Use Azure AI OTel tracer if available (provides tool definitions + full traces)
        config = {}
        try:
            from langchain_azure_ai.callbacks.tracers import AzureAIOpenTelemetryTracer
            config["callbacks"] = [AzureAIOpenTelemetryTracer()]
        except ImportError:
            pass

        result = self._agent.invoke({"messages": [("user", query)]}, config=config)

        final = result["messages"][-1].content if hasattr(result["messages"][-1], "content") else str(result["messages"][-1])

        return {"answer": final or ""}
