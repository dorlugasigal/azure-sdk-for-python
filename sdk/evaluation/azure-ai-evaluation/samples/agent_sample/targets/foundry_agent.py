import json
from random import randint
from typing import Any
from pathlib import Path
import re

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.identity import AzureCliCredential
from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from azure.ai.evaluation._engine.decorators import ExecutionContext, target, BaseTarget


@target(name="foundry_agent")
class FoundryAgent:
    
    def _normalize_agent_name(self, raw_name: str) -> str:
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

    def _load_agent_instructions(self, caller_file: str, filename: str = "instructions.txt") -> str:
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
    
    # Define a function tool for the model to use
    get_weather_tool = FunctionTool(
        name="get_weather",
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "A location like New York or San Francisco",
                },
            },
            "required": ["location"],
            "additionalProperties": False,
        },
        description="Get the weather for a given location.",
        strict=True,
    )

    def get_weather(
        self,
        location: str,
    ) -> str:
        conditions = ["sunny", "cloudy", "rainy", "stormy"]
        return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(-10, 30)}°C."

    bring_umbrella_tool = FunctionTool(
        name="bring_umbrella",
        parameters={
            "type": "object",
            "properties": {
                "weather_condition": {
                    "type": "string",
                    "description": "The current weather condition, e.g., rainy, sunny, etc.",
                },
            },
            "required": ["weather_condition"],
            "additionalProperties": False,
        },
        description="Decide whether to bring an umbrella based on the weather condition.",
        strict=True,
    )

    def bring_umbrella(
        self,
        weather_condition: str,
    ) -> str:
        if weather_condition.lower() in ["rainy", "stormy"]:
            return "Yes, you should bring an umbrella."
        else:
            return "No, you don't need an umbrella."

    def __init__(self, context: ExecutionContext, foundry_project_connection_name: str, chat_connection_name: str):
        chat_connection = context.connections_registry[chat_connection_name]
        foundry_project_connection = context.connections_registry[foundry_project_connection_name]

        self.project_client = AIProjectClient(
            endpoint=foundry_project_connection.endpoint,
            credential=AzureCliCredential(),
        )

        self.agent_name = self._normalize_agent_name(f"agent-{chat_connection.name}")

        instructions = self._load_agent_instructions(__file__, "../instructions.txt")

        self.agent = self.project_client.agents.create_version(
            agent_name=self.agent_name,
            definition=PromptAgentDefinition(
                model=chat_connection.deployment,
                tools=[self.get_weather_tool, self.bring_umbrella_tool],
                instructions=instructions,
            ),
        )

        self.openai_client = self.project_client.get_openai_client()

    def _execute_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name with the given arguments."""
        if name == "get_weather":
            return self.get_weather(**arguments)
        elif name == "bring_umbrella":
            return self.bring_umbrella(**arguments)
        else:
            return f"Unknown tool: {name}"

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
        reraise=True,
    )
    def infer(self, input: dict[str, Any]) -> dict[str, Any]:
        conversation = self.openai_client.conversations.create()

        user_input = f"context: {input['context']}\nquestion: {input['question']}"

        # Initial request to the agent
        response = self.openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent": {"name": self.agent_name, "type": "agent_reference"}},
            input=user_input,
            tool_choice="auto",
        )

        all_tool_calls = []
        total_usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        # Process tool calls in a loop until we get a text response
        max_tool_iterations = 10
        iteration = 0

        while True:
            iteration += 1
            if iteration > max_tool_iterations:
                raise RuntimeError(f"Agent exceeded maximum tool call iterations ({max_tool_iterations}). Tool calls made: {all_tool_calls}. This may indicate an infinite loop in the agent's reasoning.")
            # Check for function calls and execute them
            tool_outputs = []
            has_function_calls = False

            for item in response.output:
                if item.type == "function_call":
                    has_function_calls = True
                    all_tool_calls.append(item.name)

                    # Parse arguments and execute the tool
                    args = json.loads(item.arguments)
                    result = self._execute_tool(item.name, args)

                    # Collect function call outputs
                    tool_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": item.call_id,
                            "output": result,
                        }
                    )

            # If no function calls, we have our final response
            if not has_function_calls:
                break

            # Make another request with ONLY the tool results
            # The conversation object already tracks the history
            response = self.openai_client.responses.create(
                conversation=conversation.id,
                extra_body={"agent": {"name": self.agent_name, "type": "agent_reference"}},
                input=tool_outputs,
                tool_choice="auto",  # Allow model to respond with text now
            )

            # Accumulate token usage
            total_usage["prompt_tokens"] += response.usage.input_tokens
            total_usage["completion_tokens"] += response.usage.output_tokens
            total_usage["total_tokens"] += response.usage.total_tokens

        return {
            "answer": response.output_text,
            "tool_calls": all_tool_calls,
            "token_usage": total_usage,
            "response_id": response.id,
        }

    def close(self) -> None:
        """Close all clients and resources to release HTTP sessions."""
        self.openai_client.close()
        self.project_client.close()