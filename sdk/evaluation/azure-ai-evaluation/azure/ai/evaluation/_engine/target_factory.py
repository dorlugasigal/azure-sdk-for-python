# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Factory for creating and registering evaluation targets."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .combination_utils import generate_args_combinations, simplify_combination_names
from .config import TargetVariantConfig
from .decorators import TARGET_REGISTRY, BaseTarget as EveeBaseTarget
from .models import ExecutionContext

logger = logging.getLogger(__name__)


class TargetFactory:
    """Creates and registers evaluation targets from experiment configuration."""

    def __init__(
        self,
        config,
        execution_context: ExecutionContext,
        connections_registry: Dict[str, Any],
    ) -> None:
        self._config = config
        self._execution_context = execution_context
        self._connections_registry = connections_registry

    def register_targets(self, model_filter: Optional[List[str]] = None) -> Dict[str, Any]:
        """Register all targets from config and return the targets registry dict.

        If no targets are defined, creates a passthrough that returns
        dataset records as-is (for scoring pre-computed outputs).
        """
        targets_registry: Dict[str, Any] = {}

        targets = self._config.experiment.targets
        if not targets:
            # No targets → passthrough (score existing dataset fields directly)
            passthrough = self._create_passthrough_model("default")
            instance = passthrough(config={}, context=self._execution_context)
            targets_registry["default"] = {
                "model": instance,
                "config": TargetVariantConfig(name="default"),
                "args": {},
            }
            return targets_registry

        for target_cfg in targets:
            if model_filter and target_cfg.name not in model_filter:
                continue
            self._register_target(target_cfg, targets_registry)

        return targets_registry

    def _create_azure_ai_model_target(self, target_cfg: TargetVariantConfig) -> type:
        """Create a target that calls an Azure AI model via OpenAI client."""
        connections_registry = self._connections_registry

        class AzureAIModelTarget(EveeBaseTarget):
            # Sampling params we pass through to the OpenAI API
            _SAMPLING_PARAMS = {
                "temperature", "top_p", "max_completion_tokens", "max_tokens",
                "frequency_penalty", "presence_penalty", "seed",
            }

            def __init__(self, config=None, context=None):
                super().__init__(context)
                config = config or {}
                self._deployment = config.get("deployment_name", "gpt-4.1-mini")

                # Extract sampling params from config (variant args)
                self._sampling = {}
                for p in self._SAMPLING_PARAMS:
                    if p in config:
                        self._sampling[p] = config[p]

                # Get connection details
                conn_name = target_cfg.connection_name or "default"
                conn = connections_registry.get(conn_name, {})
                if not conn and context and hasattr(context, "connections_registry"):
                    conn = context.connections_registry.get(conn_name, {})

                if hasattr(conn, "model_dump"):
                    conn = conn.model_dump()
                elif not isinstance(conn, dict):
                    conn = {}

                azure_endpoint = conn.get("azure_endpoint", "") or conn.get("endpoint", "")

                from azure.identity import DefaultAzureCredential, get_bearer_token_provider
                from openai import OpenAI

                # Use correct token audience based on endpoint domain
                if ".services.ai.azure.com" in azure_endpoint:
                    token_scope = "https://ai.azure.com/.default"
                else:
                    token_scope = "https://cognitiveservices.azure.com/.default"

                token_provider = get_bearer_token_provider(
                    DefaultAzureCredential(), token_scope
                )

                base_url = azure_endpoint.rstrip("/")
                if not base_url.endswith("/openai/v1"):
                    base_url = base_url + "/openai/v1/"

                self._client = OpenAI(base_url=base_url, api_key=token_provider)

            def infer(self, input_data):
                query = ""
                for field in ["query", "question", "prompt", "input"]:
                    if field in input_data:
                        query = input_data[field]
                        break
                if not query:
                    if input_data:
                        query = str(list(input_data.values())[0])
                    else:
                        raise ValueError(
                            "input_data must contain at least one field "
                            "(query, question, prompt, or input)"
                        )

                response = self._client.chat.completions.create(
                    model=self._deployment,
                    messages=[{"role": "user", "content": query}],
                    **self._sampling,
                )

                answer = response.choices[0].message.content
                return {"response": answer}

        AzureAIModelTarget.__name__ = f"AzureAIModel_{target_cfg.name}"
        return AzureAIModelTarget

    def _create_azure_ai_agent_target(self, target_cfg) -> type:
        """Create a target that calls a Foundry agent via the Responses API."""
        connections_registry = self._connections_registry

        # Resolve project endpoint: connection → target config → compute → tracking
        project_endpoint = getattr(target_cfg, "azure_ai_project", None)
        if not project_endpoint:
            conn_name = getattr(target_cfg, "connection_name", None) or "default"
            conn = connections_registry.get(conn_name)
            if conn:
                if hasattr(conn, "model_dump"):
                    conn = conn.model_dump()
                project_endpoint = conn.get("azure_ai_project")
        if not project_endpoint and self._config.experiment.compute:
            project_endpoint = getattr(self._config.experiment.compute, "azure_ai_project", None)

        agent_name = target_cfg.agent_name or target_cfg.name
        agent_version = getattr(target_cfg, "agent_version", None)
        agent_instructions = getattr(target_cfg, "instructions", None)

        class AzureAIAgentTarget(EveeBaseTarget):
            """Target that calls a Foundry agent and captures both text and structured output."""

            def __init__(self, config=None, context=None):
                super().__init__(context)
                self._agent_name = agent_name
                self._agent_version = agent_version

                from azure.identity import DefaultAzureCredential
                from azure.ai.projects import AIProjectClient

                if not project_endpoint:
                    raise ValueError(
                        "azure_ai_project endpoint is required for agent targets. "
                        "Set it on the target config, connection, or compute config."
                    )

                self._project_client = AIProjectClient(
                    endpoint=project_endpoint,
                    credential=DefaultAzureCredential(),
                )
                self._client = self._project_client.get_openai_client()

            def infer(self, input_data):
                """Call the Foundry agent and return both text and structured output."""
                query = ""
                for field in ["query", "question", "prompt", "input"]:
                    if field in input_data:
                        query = input_data[field]
                        break
                if not query:
                    if input_data:
                        query = str(list(input_data.values())[0])
                    else:
                        raise ValueError(
                            "input_data must contain at least one field "
                            "(query, question, prompt, or input)"
                        )

                # Build agent reference
                agent_ref = {"name": self._agent_name, "type": "agent_reference"}
                if self._agent_version:
                    agent_ref["version"] = self._agent_version

                # Call agent via Responses API
                extra_body = {"agent_reference": agent_ref}
                if agent_instructions:
                    extra_body["instructions"] = agent_instructions

                try:
                    response = self._client.responses.create(
                        input=query,
                        extra_body=extra_body,
                    )
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to call agent '{self._agent_name}' "
                        f"(version: {self._agent_version or 'latest'}): {e}"
                    ) from e

                # Capture both plain text and structured output (includes tool calls)
                result = {"response": getattr(response, "output_text", "")}

                # Include structured output items for evaluators like task_adherence
                try:
                    output_items = []
                    if hasattr(response, "output") and response.output:
                        for item in response.output:
                            if hasattr(item, "model_dump"):
                                output_items.append(item.model_dump())
                            elif hasattr(item, "to_dict"):
                                output_items.append(item.to_dict())
                            else:
                                output_items.append(str(item))
                    else:
                        output_items = [{"type": "text", "text": result["response"]}]
                    result["output_items"] = output_items
                except (AttributeError, TypeError):
                    result["output_items"] = [{"type": "text", "text": result["response"]}]

                # Warn about unresolved function calls requiring client-side execution
                for item in getattr(response, "output", []) or []:
                    if hasattr(item, 'type') and item.type == 'function_call':
                        logger.warning(
                            "Agent '%s' returned a function_call '%s' that was not executed. "
                            "Client-side function tool execution is not supported in local evaluation. "
                            "Use Foundry-managed tools or cloud evaluation instead.",
                            agent_name, getattr(item, 'name', 'unknown'),
                        )
                        break

                return result

        AzureAIAgentTarget.__name__ = f"AzureAIAgent_{target_cfg.name}"
        return AzureAIAgentTarget

    def _register_target(
        self, target_cfg: TargetVariantConfig, targets_registry: Dict[str, Any]
    ) -> None:
        """Register a target with all argument combinations."""
        target_name = target_cfg.name
        target_type = getattr(target_cfg, "type", "custom")

        if target_type == "azure_ai_model":
            target_class = self._create_azure_ai_model_target(target_cfg)

            # deployment_name can be a list for cartesian product
            deployment_names = target_cfg.deployment_name
            if isinstance(deployment_names, str):
                deployment_names = [deployment_names]
            elif not deployment_names:
                deployment_names = ["gpt-4.1-mini"]

            # Build args list: existing args + deployment_name variations
            base_args = target_cfg.args if isinstance(target_cfg.args, list) else (
                [target_cfg.args] if target_cfg.args else []
            )
            if len(deployment_names) > 1 or base_args:
                all_args = list(base_args) + [{"deployment_name": deployment_names}]
                target_cfg_copy = target_cfg.model_copy()
                target_cfg_copy.args = all_args
                arg_combinations = generate_args_combinations(target_cfg_copy)
            else:
                arg_combinations = [{"deployment_name": deployment_names[0]}]

            named = simplify_combination_names(target_name, arg_combinations)
            for variant_name, args in named.items():
                target_instance = target_class(config=args, context=self._execution_context)
                targets_registry[variant_name] = {
                    "model": target_instance,
                    "config": target_cfg,
                    "args": args,
                }

        elif target_type == "azure_ai_agent":
            target_class = self._create_azure_ai_agent_target(target_cfg)
            arg_combinations = [{}]  # Agents don't have cartesian args
            named = simplify_combination_names(target_name, arg_combinations)
            for variant_name, args in named.items():
                target_instance = target_class(config=args, context=self._execution_context)
                targets_registry[variant_name] = {
                    "model": target_instance,
                    "config": target_cfg,
                    "args": args,
                }

        else:
            # Custom target — existing behavior
            target_class = TARGET_REGISTRY.get(target_name)
            if not target_class:
                target_class = self._create_passthrough_model(target_name)

            arg_combinations = generate_args_combinations(target_cfg)
            named = simplify_combination_names(target_name, arg_combinations)
            for variant_name, args in named.items():
                target_instance = target_class(config=args, context=self._execution_context)
                targets_registry[variant_name] = {
                    "model": target_instance,
                    "config": target_cfg,
                    "args": args,
                }

    def _create_passthrough_model(self, name: str) -> type:
        """Create a passthrough target that returns dataset record as output."""
        from .decorators import BaseTarget

        class PassthroughTarget(BaseTarget):
            def __init__(self, config: Optional[Dict[str, Any]] = None, context: Optional[Any] = None):
                super().__init__(context)

            def infer(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
                return input_data

        PassthroughTarget.__name__ = name
        return PassthroughTarget
