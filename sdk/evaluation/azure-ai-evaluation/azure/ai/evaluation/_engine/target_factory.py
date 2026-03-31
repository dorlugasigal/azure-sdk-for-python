# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Factory for creating and registering evaluation targets."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .combination_utils import generate_args_combinations, simplify_combination_names
from .config import TargetVariantConfig
from .decorators import TARGET_REGISTRY, BaseTarget as EveeBaseTarget
from .models import ExecutionContext

logger = logging.getLogger(__name__)

# ----- Target type constants -----
TARGET_TYPE_AZURE_AI_MODEL = "azure_ai_model"
TARGET_TYPE_AZURE_AI_AGENT = "azure_ai_agent"
TARGET_TYPE_CUSTOM = "custom"

# Default query field candidates (searched in order)
_DEFAULT_QUERY_CANDIDATES: List[str] = ["query", "question", "prompt", "input"]

# Default deployment when none is configured
_DEFAULT_DEPLOYMENT = "gpt-4.1-mini"


# ----- Shared helpers -----

def _extract_query_field(
    input_data: Dict[str, Any],
    candidates: Optional[List[str]] = None,
) -> str:
    """Extract the user query from *input_data* by trying known field names.

    :param input_data: Row dict coming from the dataset.
    :param candidates: Ordered field names to search. Falls back to
        ``_DEFAULT_QUERY_CANDIDATES``.
    :returns: The query string.
    :rtype: str
    :raises ValueError: If *input_data* is empty and no field matched.
    """
    candidates = candidates or _DEFAULT_QUERY_CANDIDATES
    for field in candidates:
        if field in input_data:
            return input_data[field]
    if input_data:
        return str(list(input_data.values())[0])
    raise ValueError(
        "input_data must contain at least one field "
        f"({', '.join(_DEFAULT_QUERY_CANDIDATES)})"
    )


def _resolve_connection(
    connection_name: Optional[str],
    connections_registry: Dict[str, Any],
    context: Optional[Any] = None,
) -> Dict[str, Any]:
    """Look up a connection by name and normalise it to a plain ``dict``.

    :param connection_name: Logical connection name (falls back to ``"default"``).
    :param connections_registry: The factory-level connections dict.
    :param context: Optional execution context that may carry its own registry.
    :returns: A plain ``dict`` with connection fields.
    :rtype: dict
    """
    conn_name = connection_name or "default"
    conn = connections_registry.get(conn_name, {})
    if not conn and context and hasattr(context, "connections_registry"):
        conn = context.connections_registry.get(conn_name, {})

    if hasattr(conn, "model_dump"):
        conn = conn.model_dump()
    elif not isinstance(conn, dict):
        conn = {}
    return conn


def _setup_azure_openai_client(azure_endpoint: str) -> "openai.OpenAI":
    """Create an :class:`openai.OpenAI` client authenticated via ``DefaultAzureCredential``.

    :param azure_endpoint: The Azure AI endpoint URL.
    :returns: Configured OpenAI client.
    :rtype: openai.OpenAI
    """
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import OpenAI

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://ai.azure.com/.default",
    )

    base_url = f"{azure_endpoint.rstrip('/')}/openai/v1"

    return OpenAI(base_url=base_url, api_key=token_provider)


def _parse_agent_output(response: Any, fallback_text: str) -> List[Dict[str, Any]]:
    """Serialise structured ``response.output`` items to plain dicts.

    :param response: The Responses-API response object.
    :param fallback_text: Plain-text answer used when no output items exist.
    :returns: List of serialised output items.
    :rtype: list[dict]
    """
    try:
        if hasattr(response, "output") and response.output:
            items: List[Dict[str, Any]] = []
            for item in response.output:
                if hasattr(item, "model_dump"):
                    items.append(item.model_dump())
                elif hasattr(item, "to_dict"):
                    items.append(item.to_dict())
                else:
                    items.append(str(item))
            return items
        return [{"type": "text", "text": fallback_text}]
    except (AttributeError, TypeError):
        return [{"type": "text", "text": fallback_text}]


def _warn_unexecuted_function_calls(response: Any, agent_name: str) -> None:
    """Log a warning if the agent returned a ``function_call`` that was not executed.

    :param response: The Responses-API response object.
    :param agent_name: Display name used in the warning message.
    """
    for item in getattr(response, "output", []) or []:
        if hasattr(item, "type") and item.type == "function_call":
            logger.warning(
                "Agent '%s' returned a function_call '%s' that was not executed. "
                "Client-side function tool execution is not supported in local "
                "evaluation. Use Foundry-managed tools or cloud evaluation instead.",
                agent_name,
                getattr(item, "name", "unknown"),
            )
            break


class TargetFactory:
    """Creates and registers evaluation targets from experiment configuration.

    :param config: Experiment configuration object.
    :param execution_context: Shared execution context for all targets.
    :param connections_registry: Named connection definitions.
    """

    def __init__(
        self,
        config: Any,
        execution_context: ExecutionContext,
        connections_registry: Dict[str, Any],
    ) -> None:
        self._config = config
        self._execution_context = execution_context
        self._connections_registry = connections_registry

        # Dispatch table: target_type → (class_factory, arg_combinator)
        self._target_dispatchers: Dict[
            str,
            tuple[
                Callable[[TargetVariantConfig], type],
                Callable[[TargetVariantConfig], List[Dict[str, Any]]],
            ],
        ] = {
            TARGET_TYPE_AZURE_AI_MODEL: (
                self._create_azure_ai_model_target,
                self._compute_model_arg_combinations,
            ),
            TARGET_TYPE_AZURE_AI_AGENT: (
                self._create_azure_ai_agent_target,
                self._compute_agent_arg_combinations,
            ),
        }

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def register_targets(
        self, model_filter: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Register all targets from config and return the targets registry dict.

        If no targets are defined, creates a passthrough that returns
        dataset records as-is (for scoring pre-computed outputs).

        :param model_filter: Optional list of target names to include.
        :returns: Mapping of variant-name → target entry dict.
        :rtype: dict[str, Any]
        """
        targets_registry: Dict[str, Any] = {}

        targets = self._config.experiment.targets
        if not targets:
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

    # ------------------------------------------------------------------ #
    #  Target class factories
    # ------------------------------------------------------------------ #

    def _create_azure_ai_model_target(
        self, target_cfg: TargetVariantConfig,
    ) -> type:
        """Create a target class that calls an Azure AI model via the OpenAI client.

        :param target_cfg: Configuration for this target variant.
        :returns: A dynamically created target class.
        :rtype: type
        """
        connections_registry = self._connections_registry

        class AzureAIModelTarget(EveeBaseTarget):
            """Wraps an Azure-hosted model behind the OpenAI chat API."""

            _SAMPLING_PARAMS = {
                "temperature", "top_p", "max_completion_tokens", "max_tokens",
                "frequency_penalty", "presence_penalty", "seed",
            }

            def __init__(self, config: Optional[Dict[str, Any]] = None,
                         context: Optional[Any] = None) -> None:
                super().__init__(context)
                config = config or {}
                self._deployment = config.get("deployment_name", _DEFAULT_DEPLOYMENT)
                self._sampling = {
                    p: config[p] for p in self._SAMPLING_PARAMS if p in config
                }

                conn = _resolve_connection(
                    target_cfg.connection_name, connections_registry, context,
                )
                azure_endpoint = conn.get("azure_endpoint", "")
                self._client = _setup_azure_openai_client(azure_endpoint)

            def infer(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
                """Send a chat completion request and return the response.

                :param input_data: Row dict from the dataset.
                :returns: ``{"response": <model answer>}``
                :rtype: dict
                """
                query = _extract_query_field(input_data)
                response = self._client.chat.completions.create(
                    model=self._deployment,
                    messages=[{"role": "user", "content": query}],
                    **self._sampling,
                )
                return {"response": response.choices[0].message.content}

        AzureAIModelTarget.__name__ = f"AzureAIModel_{target_cfg.name}"
        return AzureAIModelTarget

    def _create_azure_ai_agent_target(
        self, target_cfg: TargetVariantConfig,
    ) -> type:
        """Create a target class that calls a Foundry agent via the Responses API.

        :param target_cfg: Configuration for this target variant.
        :returns: A dynamically created target class.
        :rtype: type
        """
        project_endpoint = self._resolve_project_endpoint(target_cfg)
        agent_name = target_cfg.agent_name or target_cfg.name
        agent_version = getattr(target_cfg, "agent_version", None)
        agent_instructions = getattr(target_cfg, "instructions", None)

        class AzureAIAgentTarget(EveeBaseTarget):
            """Target that calls a Foundry agent and captures text + structured output."""

            def __init__(self, config: Optional[Dict[str, Any]] = None,
                         context: Optional[Any] = None) -> None:
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

            def infer(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
                """Call the Foundry agent and return text + structured output.

                :param input_data: Row dict from the dataset.
                :returns: ``{"response": ..., "output_items": [...]}``
                :rtype: dict
                """
                query = _extract_query_field(input_data)

                agent_ref, extra_body = _build_agent_reference(
                    self._agent_name, self._agent_version, agent_instructions,
                )

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

                result: Dict[str, Any] = {
                    "response": getattr(response, "output_text", ""),
                }
                result["output_items"] = _parse_agent_output(
                    response, result["response"],
                )
                _warn_unexecuted_function_calls(response, agent_name)
                return result

        AzureAIAgentTarget.__name__ = f"AzureAIAgent_{target_cfg.name}"
        return AzureAIAgentTarget

    # ------------------------------------------------------------------ #
    #  Agent helpers
    # ------------------------------------------------------------------ #

    def _resolve_project_endpoint(
        self, target_cfg: TargetVariantConfig,
    ) -> Optional[str]:
        """Resolve the Azure AI project endpoint using multiple fallbacks.

        Resolution order: ``target_cfg.azure_ai_project`` → connection →
        ``compute.azure_ai_project``.

        :param target_cfg: Target variant configuration.
        :returns: Endpoint URL or ``None``.
        :rtype: str | None
        """
        endpoint = getattr(target_cfg, "azure_ai_project", None)
        if endpoint:
            return endpoint

        conn_name = getattr(target_cfg, "connection_name", None) or "default"
        conn = self._connections_registry.get(conn_name)
        if conn:
            if hasattr(conn, "model_dump"):
                conn = conn.model_dump()
            endpoint = conn.get("azure_ai_project")
            if endpoint:
                return endpoint

        if self._config.experiment.compute:
            return getattr(
                self._config.experiment.compute, "azure_ai_project", None,
            )
        return None

    # ------------------------------------------------------------------ #
    #  Registration & arg combination helpers
    # ------------------------------------------------------------------ #

    def _register_target(
        self,
        target_cfg: TargetVariantConfig,
        targets_registry: Dict[str, Any],
    ) -> None:
        """Register a target with all argument combinations.

        :param target_cfg: Configuration for this target variant.
        :param targets_registry: Mutable registry to populate.
        """
        target_name = target_cfg.name
        target_type = getattr(target_cfg, "type", TARGET_TYPE_CUSTOM)

        dispatcher = self._target_dispatchers.get(target_type)
        if dispatcher:
            class_factory, arg_combinator = dispatcher
            target_class = class_factory(target_cfg)
            arg_combinations = arg_combinator(target_cfg)
        else:
            # Custom target — existing behaviour
            target_class = TARGET_REGISTRY.get(target_name)
            if not target_class:
                target_class = self._create_passthrough_model(target_name)
            arg_combinations = generate_args_combinations(target_cfg)

        self._instantiate_variants(
            target_name, target_class, target_cfg, arg_combinations, targets_registry,
        )

    @staticmethod
    def _compute_model_arg_combinations(
        target_cfg: TargetVariantConfig,
    ) -> List[Dict[str, Any]]:
        """Compute argument combinations for an Azure AI model target.

        Handles ``deployment_name`` as a list for cartesian-product expansion.

        :param target_cfg: Target variant configuration.
        :returns: List of per-variant argument dicts.
        :rtype: list[dict]
        """
        deployment_names = target_cfg.deployment_name
        if isinstance(deployment_names, str):
            deployment_names = [deployment_names]
        elif not deployment_names:
            deployment_names = [_DEFAULT_DEPLOYMENT]

        base_args: List[Any] = (
            target_cfg.args
            if isinstance(target_cfg.args, list)
            else ([target_cfg.args] if target_cfg.args else [])
        )

        if len(deployment_names) > 1 or base_args:
            all_args = list(base_args) + [{"deployment_name": deployment_names}]
            target_cfg_copy = target_cfg.model_copy()
            target_cfg_copy.args = all_args
            return generate_args_combinations(target_cfg_copy)

        return [{"deployment_name": deployment_names[0]}]

    @staticmethod
    def _compute_agent_arg_combinations(
        target_cfg: TargetVariantConfig,
    ) -> List[Dict[str, Any]]:
        """Return argument combinations for an agent target (always a single empty set).

        :param target_cfg: Target variant configuration (unused for agents).
        :returns: ``[{}]``
        :rtype: list[dict]
        """
        return [{}]

    def _instantiate_variants(
        self,
        target_name: str,
        target_class: type,
        target_cfg: TargetVariantConfig,
        arg_combinations: List[Dict[str, Any]],
        targets_registry: Dict[str, Any],
    ) -> None:
        """Instantiate all variants and insert them into *targets_registry*.

        :param target_name: Base name of the target.
        :param target_class: The target class to instantiate.
        :param target_cfg: Original target configuration.
        :param arg_combinations: List of argument dicts to generate variants.
        :param targets_registry: Mutable registry to populate.
        """
        named = simplify_combination_names(target_name, arg_combinations)
        for variant_name, args in named.items():
            target_instance = target_class(
                config=args, context=self._execution_context,
            )
            targets_registry[variant_name] = {
                "model": target_instance,
                "config": target_cfg,
                "args": args,
            }

    # ------------------------------------------------------------------ #
    #  Passthrough
    # ------------------------------------------------------------------ #

    @staticmethod
    def _create_passthrough_model(name: str) -> type:
        """Create a passthrough target that returns the dataset record as output.

        :param name: Class name to assign to the generated type.
        :returns: Passthrough target class.
        :rtype: type
        """
        from .decorators import BaseTarget

        class PassthroughTarget(BaseTarget):
            """Returns input data unchanged — used when no real target is configured."""

            def __init__(self, config: Optional[Dict[str, Any]] = None,
                         context: Optional[Any] = None) -> None:
                super().__init__(context)

            def infer(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
                return input_data

        PassthroughTarget.__name__ = name
        return PassthroughTarget


# ----- Module-level agent helper -----

def _build_agent_reference(
    agent_name: str,
    agent_version: Optional[str],
    instructions: Optional[str],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Build the agent reference dict and ``extra_body`` for the Responses API.

    :param agent_name: The logical agent name.
    :param agent_version: Optional version pin.
    :param instructions: Optional instruction override.
    :returns: ``(agent_ref, extra_body)`` tuple.
    :rtype: tuple[dict, dict]
    """
    agent_ref: Dict[str, Any] = {"name": agent_name, "type": "agent_reference"}
    if agent_version:
        agent_ref["version"] = agent_version

    extra_body: Dict[str, Any] = {"agent_reference": agent_ref}
    if instructions:
        extra_body["instructions"] = instructions

    return agent_ref, extra_body
