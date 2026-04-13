from __future__ import annotations

import asyncio
from typing import Annotated, Any

from pydantic import Field

from azure.ai.evaluation._engine.decorators import ExecutionContext, target, BaseTarget

from agent_framework import tool
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.ai.projects.aio import AIProjectClient

import re
from random import randint
from pathlib import Path
from azure.identity.aio import AzureCliCredential
from tenacity import retry, stop_after_attempt, wait_exponential

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
        self.agent_name = normalize_agent_name(f"lotr-agent-{context.model_variant_id}")
        self.instructions = load_agent_instructions(__file__, instructions_path)
        self.credential = AzureCliCredential()
        self.tools = WeatherTools()
        self.project_client = AIProjectClient(endpoint=chat_connection.endpoint, credential=self.credential)
        self.provider = AzureAIProjectAgentProvider(project_client=self.project_client)
        self.model_deployment_name = chat_connection.deployment
        self.agent = None  # Will be created asynchronously in _ensure_agent()
        self._agent_lock = asyncio.Lock()
        
    async def _ensure_agent(self):
        """Create the agent if not already created."""
        if self.agent is None:
            async with self._agent_lock:
                if self.agent is None:  # Double-check inside lock
                    self.agent = await self.provider.create_agent(
                        name=self.agent_name,
                        model=self.model_deployment_name,
                        instructions=self.instructions,
                        tools=[self.tools.get_weather, self.tools.bring_umbrella],
                    )
                    return self.agent
                
    async def infer(self, input: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_agent()
        response = await self.agent.run(f"context: {input['context']}\nquestion: {input['question']}")
        tool_calls = [message.contents[0].name for message in response.raw_representation.messages if message.contents[0].type == "function_call"]

        usage = response.usage_details
        return {
            "answer": response.text,
            "tool_calls": tool_calls,
            "token_usage": {
                "prompt_tokens": usage.get("input_token_count", 0),
                "completion_tokens": usage.get("output_token_count", 0),
                "total_tokens": usage.get("total_token_count", 0),
            },
            "response_id": response.response_id,
        }

    async def close(self) -> None:
        """Close all clients to release HTTP sessions."""
        await self.project_client.close()
        await self.credential.close()