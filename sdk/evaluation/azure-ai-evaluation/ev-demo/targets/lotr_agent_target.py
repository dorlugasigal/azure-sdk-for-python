from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

from pydantic import Field

from azure.ai.evaluation._engine.decorators import ExecutionContext, target, BaseTarget

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient

import re
from random import randint
from pathlib import Path
from azure.identity.aio import AzureCliCredential
from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential as SyncAzureCliCredential
from azure.core.rest import HttpRequest

def normalize_agent_name(raw_name: str) -> str:
    """
    Normalize agent name to meet Azure Foundry requirements:
    - Start and end with alphanumeric characters
    - Can contain hyphens in the middle
    - Must not exceed 63 characters
    """
    # Replace non-alphanumeric characters (except hyphens) with hyphens
    agent_name = re.sub(r"[^a-zA-Z0-9-]+", "-", raw_name)
    # Remove leading/trailing hyphens
    agent_name = agent_name.strip("-")
    # Replace multiple consecutive hyphens with a single hyphen
    agent_name = re.sub(r"-+", "-", agent_name)
    # Truncate to 63 characters, ensuring it ends with alphanumeric
    if len(agent_name) > 63:
        agent_name = agent_name[:63].rstrip("-")

    return agent_name

def load_agent_instructions(caller_file: str | Path, filename: str = "instructions.txt") -> str:
    """Load instructions from a text file relative to the caller's location.

    Args:
        caller_file: The __file__ of the calling module (used to resolve the relative path).
        filename: The name of the instructions file. Defaults to "instructions.txt".

    Returns:
        The contents of the instructions file, stripped of leading/trailing whitespace.
    """
    instructions_file = Path(caller_file).parent / filename
    with open(instructions_file, encoding="utf-8") as f:
        return f.read().strip()

class WeatherTools:
    @tool
    def get_weather(
        self,
        location: Annotated[str, Field(description="The location to get the weather for.")],
    ) -> str:
        """Get the weather for a given location."""
        conditions = ["sunny", "cloudy", "rainy", "stormy"]
        return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(-10, 30)}°C."

    @tool
    def bring_umbrella(
        self,
        weather_condition: Annotated[str, Field(description="The current weather condition, e.g., rainy, sunny, etc.")],
    ) -> str:
        """Decide whether to bring an umbrella based on the weather condition."""
        if weather_condition.lower() in ["rainy", "stormy"]:
            return "Yes, you should bring an umbrella."
        else:
            return "No, you don't need an umbrella."


@target(name="lotr_agent")
class WeatherAgentLocalTarget(BaseTarget):
    def __init__(self, context: ExecutionContext, chat_connection_name: str, instructions_path: str):
        chat_connection = context.connections_registry[chat_connection_name]
        self._agent_name = normalize_agent_name(f"lotr-agent-{context.model_variant_id}")
        self._instructions = load_agent_instructions(__file__, instructions_path)
        self._tools = WeatherTools()
        self._project_endpoint = chat_connection.azure_ai_project
        self._deployment = chat_connection.deployment

        # Derive azure_endpoint for OpenAIChatClient (needs base URL without /openai/v1)
        ep = chat_connection.endpoint.rstrip("/")
        self._azure_endpoint = ep[: -len("/openai/v1")] if ep.endswith("/openai/v1") else ep

        # Deploy agent to Foundry (visible in portal)
        self._ensure_foundry_agent()

    def _ensure_foundry_agent(self):
        """Create or update the agent in Foundry via REST API."""
        client = AIProjectClient(
            endpoint=self._project_endpoint,
            credential=SyncAzureCliCredential(),
        )
        tool_defs = [
            {"type": "function", "name": "get_weather",
             "description": "Get the weather for a given location.",
             "parameters": {"type": "object", "properties": {"location": {"type": "string", "description": "The location to get the weather for."}}, "required": ["location"]}},
            {"type": "function", "name": "bring_umbrella",
             "description": "Decide whether to bring an umbrella based on the weather condition.",
             "parameters": {"type": "object", "properties": {"weather_condition": {"type": "string", "description": "The current weather condition, e.g., rainy, sunny, etc."}}, "required": ["weather_condition"]}},
        ]
        payload = {
            "name": self._agent_name,
            "definition": {
                "kind": "prompt",
                "model": self._deployment,
                "instructions": self._instructions,
                "tools": tool_defs,
            },
        }
        # Try create; if agent exists, update it with a new version
        req = HttpRequest(method="POST", url="/agents?api-version=v1", json=payload)
        resp = client.send_request(req)
        if resp.status_code == 409:
            # Agent exists — update with new version
            req = HttpRequest(method="POST", url=f"/agents/{self._agent_name}/versions?api-version=v1", json=payload)
            resp = client.send_request(req)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Failed to create/update Foundry agent '{self._agent_name}': {resp.content}")
        client.close()

    def infer(self, input: dict[str, Any]) -> dict[str, Any]:
        """Sync infer — agent deployed in Foundry, runs via OpenAIChatClient.

        FoundryChatClient hangs across multiple asyncio.run() calls due to
        stale async state. OpenAIChatClient works reliably per-call.
        """
        async def _run():
            agent = Agent(
                client=OpenAIChatClient(
                    model=self._deployment,
                    azure_endpoint=self._azure_endpoint,
                    credential=AzureCliCredential(),
                ),
                name=self._agent_name,
                instructions=self._instructions,
                tools=[self._tools.get_weather, self._tools.bring_umbrella],
                default_options={"store": False},
            )
            return await agent.run(f"context: {input['context']}\nquestion: {input['question']}")

        response = asyncio.run(_run())

        tool_calls = []
        for message in (response.raw_representation.messages if response.raw_representation else []):
            for content in (message.contents if hasattr(message, 'contents') else []):
                if hasattr(content, 'type') and content.type == "function_call":
                    tool_calls.append(content.name)

        usage = response.usage_details
        return {
            "response": response.text,
            "tool_calls": tool_calls,
            "token_usage": {
                "prompt_tokens": usage.get("input_token_count", 0) if usage else 0,
                "completion_tokens": usage.get("output_token_count", 0) if usage else 0,
                "total_tokens": usage.get("total_token_count", 0) if usage else 0,
            },
            "response_id": response.response_id,
        }