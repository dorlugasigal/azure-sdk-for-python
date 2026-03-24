"""Model evaluator for running experiments."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config, DatasetConfig, EvaluatorConfig, TargetVariantConfig
from .decorators import DATASET_REGISTRY, EVALUATOR_REGISTRY, TARGET_REGISTRY, BaseDataset, BaseTarget as EveeBaseTarget
from .discovery import discover_components
from .models import EvaluationOutput, ExecutionContext, InferenceOutput
from .otel_trace_capture import OTelTraceCapture
from .tracking import (
    TrackingBackend,
    create_tracking_backend,
    OperationStatus,
    ExperimentStartEvent,
    ModelRunStartEvent,
    ModelRunCompletedEvent,
    InferenceStartEvent,
    InferenceCompletedEvent,
    ResultsAnalyzedEvent,
    ArtifactGeneratedEvent,
    ExperimentCompletedEvent,
)


def _extract_tool_definitions_from_trace(agent_trace) -> list:
    """Extract tool definitions from OTel trace spans if available.

    The OpenAI instrumentation captures tool definitions in the
    gen_ai.tool.definitions span attribute when available.
    """
    for span in agent_trace.spans:
        tool_defs = span.attributes.get("gen_ai.tool.definitions")
        if tool_defs:
            import json
            if isinstance(tool_defs, str):
                try:
                    return json.loads(tool_defs)
                except (json.JSONDecodeError, ValueError):
                    pass
            elif isinstance(tool_defs, (list, tuple)):
                return list(tool_defs)
    return []


def _normalize_output_items(items: list) -> list:
    """Normalize output_items from any framework to the OpenAI message schema.

    SDK evaluators expect:
      - content (not contents)
      - tool_call (not function_call)
      - tool_result (not function_result)

    This handles MAF format, OpenAI format, LangChain format.
    """
    import json as _json
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "")
        # MAF uses "contents", OpenAI uses "content"
        raw_content = item.get("content") or item.get("contents")

        if role == "assistant":
            new_content = []
            if isinstance(raw_content, list):
                for c in raw_content:
                    if not isinstance(c, dict):
                        new_content.append({"type": "text", "text": str(c)})
                        continue
                    ctype = c.get("type", "")
                    if ctype in ("function_call", "tool_call"):
                        args = c.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = _json.loads(args)
                            except (ValueError, _json.JSONDecodeError):
                                pass
                        new_content.append({
                            "type": "tool_call",
                            "tool_call_id": c.get("tool_call_id") or c.get("call_id", ""),
                            "name": c.get("name", ""),
                            "arguments": args,
                        })
                    elif ctype == "text":
                        new_content.append({"type": "text", "text": c.get("text", "")})
                    else:
                        new_content.append(c)
            elif isinstance(raw_content, str) and raw_content:
                new_content = [{"type": "text", "text": raw_content}]

            # Handle LangChain-style tool_calls at message level
            if "tool_calls" in item and isinstance(item["tool_calls"], list):
                for tc in item["tool_calls"]:
                    if isinstance(tc, dict):
                        args = tc.get("arguments") or tc.get("args", {})
                        if isinstance(args, str):
                            try:
                                args = _json.loads(args)
                            except (ValueError, _json.JSONDecodeError):
                                pass
                        new_content.append({
                            "type": "tool_call",
                            "tool_call_id": tc.get("tool_call_id") or tc.get("id") or tc.get("call_id", ""),
                            "name": tc.get("name", ""),
                            "arguments": args,
                        })

            if new_content:
                normalized.append({"role": "assistant", "content": new_content})

        elif role == "tool":
            if isinstance(raw_content, list):
                new_content = []
                for c in raw_content:
                    if isinstance(c, dict) and c.get("type") in ("function_result", "tool_result"):
                        call_id = c.get("tool_call_id") or c.get("call_id", "")
                        result_val = c.get("tool_result") or c.get("result", "")
                        new_content.append({
                            "type": "tool_result",
                            "tool_call_id": call_id,
                            "tool_result": str(result_val),
                        })
                    else:
                        new_content.append(c)
                tool_call_id = item.get("tool_call_id", "")
                if not tool_call_id and raw_content and isinstance(raw_content[0], dict):
                    tool_call_id = raw_content[0].get("call_id", "")
                normalized.append({"role": "tool", "tool_call_id": tool_call_id, "content": new_content})
            elif isinstance(raw_content, str):
                normalized.append({
                    "role": "tool",
                    "tool_call_id": item.get("tool_call_id", ""),
                    "content": [{"type": "tool_result", "tool_call_id": item.get("tool_call_id", ""), "tool_result": raw_content}],
                })
        else:
            normalized.append(item)

    return normalized


def _normalize_tool_definitions(tool_defs: list) -> list:
    """Normalize tool definitions to the flat format SDK evaluators expect.

    Evaluators expect: {"name": "...", "type": "function", "description": "...", "parameters": {...}}
    
    Handles:
    - Raw Python functions (with annotations/docstrings)
    - MAF FunctionTool objects (have .to_json_schema_spec())
    - LangChain tools (have .name, .description, .args_schema)
    - OpenAI nested format: {"type": "function", "function": {"name": ...}} → flattened
    - Already-flat dicts (pass through)
    """
    normalized = []
    for tool in tool_defs:
        if isinstance(tool, dict):
            normalized.append(_flatten_tool_def(tool))
        elif hasattr(tool, "to_json_schema_spec"):
            # MAF FunctionTool
            normalized.append(_flatten_tool_def(tool.to_json_schema_spec()))
        elif hasattr(tool, "args_schema") and hasattr(tool, "name"):
            # LangChain tool
            schema = {}
            if tool.args_schema:
                try:
                    schema = tool.args_schema.model_json_schema()
                except Exception:
                    pass
            normalized.append({
                "name": tool.name,
                "type": "function",
                "description": getattr(tool, "description", ""),
                "parameters": schema,
            })
        elif callable(tool):
            # Raw Python function — extract from signature + docstring
            import inspect
            sig = inspect.signature(tool)
            props = {}
            required = []
            for pname, param in sig.parameters.items():
                if pname == "self":
                    continue
                prop = {"type": "string"}
                annotation = param.annotation
                if annotation != inspect.Parameter.empty:
                    ann_str = str(annotation)
                    if "int" in ann_str:
                        prop["type"] = "integer"
                    elif "float" in ann_str:
                        prop["type"] = "number"
                    elif "bool" in ann_str:
                        prop["type"] = "boolean"
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
                props[pname] = prop
            normalized.append({
                "name": getattr(tool, "__name__", "unknown"),
                "type": "function",
                "description": getattr(tool, "__doc__", "") or "",
                "parameters": {"type": "object", "properties": props, "required": required},
            })
        else:
            normalized.append({"name": str(tool), "type": "function"})
    return normalized


def _flatten_tool_def(d: dict) -> dict:
    """Flatten nested OpenAI format to flat format for evaluators.
    
    {"type": "function", "function": {"name": "x", ...}} → {"name": "x", "type": "function", ...}
    """
    if "function" in d and isinstance(d["function"], dict) and "name" in d["function"]:
        flat = {"type": d.get("type", "function")}
        flat.update(d["function"])
        return flat
    return d
    return normalized


class ModelEvaluator:
    """Main evaluator for assessing AI models."""

    def __init__(
        self,
        config_path: str = "config.yaml",
        load_config_only: bool = False,
        model_filter: Optional[List[str]] = None,
        tracking_enabled: bool = True,
    ) -> None:
        """Initialize evaluator.

        Args:
            config_path: Path to configuration YAML file
            load_config_only: Whether to only load configuration
            model_filter: Optional list of model names to evaluate
            tracking_enabled: Whether to enable tracking backend
        """
        self.model_filter = model_filter

        # Auto-discover components
        discover_components()

        # Load config
        self.config = Config.from_yaml(config_path)

        # Create tracking backend
        self.tracking_backend: TrackingBackend = create_tracking_backend(
            config=self.config,
            tracking_enabled=tracking_enabled,
        )
        self.tracking_backend.on_startup()

        # Set up OTel trace capture — auto-enabled when OTel SDK is available
        self._trace_capture: Optional[OTelTraceCapture] = None
        trace_capture = OTelTraceCapture(capture_content=True)
        if trace_capture.setup():
            self._trace_capture = trace_capture

        if load_config_only:
            return

        # Create output directory
        self._current_dir = Path.cwd()
        self._current_experiment_dir = self._create_experiment_dir()

        # Register connections
        self.connections_registry: Dict[str, Any] = {}
        connections = self.config.experiment.connections
        if isinstance(connections, list):
            for connection in connections:
                if hasattr(connection, "name"):
                    self.connections_registry[connection.name] = connection
                elif isinstance(connection, dict):
                    self.connections_registry[connection.get("name", "default")] = connection

        # Build execution context
        self.execution_context = ExecutionContext(
            connections_registry=self.connections_registry,
            experiment_name=self.config.experiment.name,
            experiment_version=self.config.experiment.version,
            experiment_dir=self._current_experiment_dir,
            output_path=self.config.experiment.output_path,
            tracking_enabled=False,
        )

        # Register targets and evaluators
        self.targets_registry = {}
        self.evaluators_registry = {}

        self._register_targets()
        self._register_evaluators()

    def _create_experiment_dir(self) -> Path:
        """Create experiment directory."""
        name = self.config.experiment.name.replace(" ", "_")
        version = self.config.experiment.version
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        exp_dir = f"{name}_v{version}__{timestamp}"

        output_path = self._current_dir / self.config.experiment.output_path / exp_dir
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    def _register_targets(self) -> None:
        """Register targets from configuration.
        
        If no targets are defined, creates a passthrough that returns
        dataset records as-is (for scoring pre-computed outputs).
        """
        targets = self.config.experiment.targets
        if not targets:
            # No targets → passthrough (score existing dataset fields directly)
            passthrough = self._create_passthrough_model("default")
            instance = passthrough(config={}, context=self.execution_context)
            self.targets_registry["default"] = {
                "model": instance,
                "config": TargetVariantConfig(name="default"),
                "args": {},
            }
            return

        for target_cfg in targets:
            if self.model_filter and target_cfg.name not in self.model_filter:
                continue
            self._register_target(target_cfg)

    def _create_azure_ai_model_target(self, target_cfg: TargetVariantConfig) -> type:
        """Create a target that calls an Azure AI model via OpenAI client."""
        connections_registry = self.connections_registry

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

                azure_endpoint = conn.get("azure_endpoint", "")

                from azure.identity import DefaultAzureCredential, get_bearer_token_provider
                from openai import OpenAI

                token_provider = get_bearer_token_provider(
                    DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
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
                return {"answer": answer}

        AzureAIModelTarget.__name__ = f"AzureAIModel_{target_cfg.name}"
        return AzureAIModelTarget

    def _create_azure_ai_agent_target(self, target_cfg) -> type:
        """Create a target that calls a Foundry agent via the Responses API."""
        # Resolve project endpoint from target config, compute config, or tracking config
        project_endpoint = getattr(target_cfg, "azure_ai_project", None)
        if not project_endpoint and self.config.experiment.compute:
            project_endpoint = getattr(self.config.experiment.compute, "azure_ai_project", None)
        if not project_endpoint and self.config.experiment.tracking_backend:
            project_endpoint = getattr(self.config.experiment.tracking_backend, "azure_ai_project", None)

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
                        "Set it on the target config, compute config, or tracking_backend config."
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
                result = {"answer": getattr(response, "output_text", "")}

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
                        output_items = [{"type": "text", "text": result["answer"]}]
                    result["output_items"] = output_items
                except (AttributeError, TypeError):
                    result["output_items"] = [{"type": "text", "text": result["answer"]}]

                # Warn about unresolved function calls requiring client-side execution
                import logging as _log
                for item in getattr(response, "output", []) or []:
                    if hasattr(item, 'type') and item.type == 'function_call':
                        _log.getLogger(__name__).warning(
                            "Agent '%s' returned a function_call '%s' that was not executed. "
                            "Client-side function tool execution is not supported in local evaluation. "
                            "Use Foundry-managed tools or cloud evaluation instead.",
                            agent_name, getattr(item, 'name', 'unknown'),
                        )
                        break

                return result

        AzureAIAgentTarget.__name__ = f"AzureAIAgent_{target_cfg.name}"
        return AzureAIAgentTarget

    def _register_target(self, target_cfg: TargetVariantConfig) -> None:
        """Register a target with all argument combinations."""
        import logging as _logging

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
                arg_combinations = self._generate_args_combinations(target_cfg_copy)
            else:
                arg_combinations = [{"deployment_name": deployment_names[0]}]

            named = self._simplify_combination_names(target_name, arg_combinations)
            for variant_name, args in named.items():
                target_instance = target_class(config=args, context=self.execution_context)
                self.targets_registry[variant_name] = {
                    "model": target_instance,
                    "config": target_cfg,
                    "args": args,
                }

        elif target_type == "azure_ai_agent":
            target_class = self._create_azure_ai_agent_target(target_cfg)
            arg_combinations = [{}]  # Agents don't have cartesian args
            named = self._simplify_combination_names(target_name, arg_combinations)
            for variant_name, args in named.items():
                target_instance = target_class(config=args, context=self.execution_context)
                self.targets_registry[variant_name] = {
                    "model": target_instance,
                    "config": target_cfg,
                    "args": args,
                }

        else:
            # Custom target — existing behavior
            target_class = TARGET_REGISTRY.get(target_name)
            if not target_class:
                target_class = self._create_passthrough_model(target_name)

            arg_combinations = self._generate_args_combinations(target_cfg)
            named = self._simplify_combination_names(target_name, arg_combinations)
            for variant_name, args in named.items():
                target_instance = target_class(config=args, context=self.execution_context)
                self.targets_registry[variant_name] = {
                    "model": target_instance,
                    "config": target_cfg,
                    "args": args,
                }

    def _generate_args_combinations(self, model_cfg: TargetVariantConfig) -> List[Dict[str, Any]]:
        """Generate all argument combinations (Cartesian product)."""
        if not model_cfg.args:
            return [{}]

        arg_dicts = []
        args_list = model_cfg.args if isinstance(model_cfg.args, list) else [model_cfg.args]
        for arg in args_list:
            if isinstance(arg, dict):
                for key, values in arg.items():
                    if isinstance(values, list):
                        arg_dicts.append({key: values})
                    else:
                        arg_dicts.append({key: [values]})

        if not arg_dicts:
            return [{}]

        keys = [list(d.keys())[0] for d in arg_dicts]
        value_lists = [list(d.values())[0] for d in arg_dicts]

        combinations = []
        for values in product(*value_lists):
            combinations.append(dict(zip(keys, values)))

        return combinations

    def _create_passthrough_model(self, name: str) -> type:
        """Create a passthrough model that returns dataset record as output."""
        from .decorators import BaseModel as EveeBaseModel

        class PassthroughModel(EveeBaseModel):
            def __init__(self, config: Optional[Dict[str, Any]] = None, context: Optional[Any] = None):
                super().__init__(context)

            def infer(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
                return input_data

        PassthroughModel.__name__ = name
        return PassthroughModel

    def _generate_variant_name(self, model_name: str, args: Dict[str, Any]) -> str:
        """Generate unique variant name."""
        if not args:
            return model_name

        suffix = "_".join(f"{k}={v}" for k, v in sorted(args.items()))
        return f"{model_name}__{suffix}"

    def _simplify_combination_names(
        self, model_name: str, arg_combinations: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Generate simplified names using only the parameters that vary.

        If args are {"prompt": "baseline", "temp": 0.7, "max_tokens": 200} and
        {"prompt": "few_shot", "temp": 0.7, "max_tokens": 200}, the only varying
        key is "prompt", so names become "model__baseline" and "model__few_shot"
        instead of including all parameters.
        """
        if not arg_combinations:
            return {}

        if len(arg_combinations) == 1:
            name = self._generate_variant_name(model_name, arg_combinations[0])
            return {name: arg_combinations[0]}

        # Find keys that vary across combinations
        varying_keys = set()
        for key in arg_combinations[0]:
            values = {str(args.get(key)) for args in arg_combinations}
            if len(values) > 1:
                varying_keys.add(key)

        # If nothing varies (shouldn't happen), fall back to full name
        if not varying_keys:
            return {
                self._generate_variant_name(model_name, args): args
                for args in arg_combinations
            }

        # Build simplified names from varying key=value pairs
        result = {}
        for args in arg_combinations:
            parts = [f"{k}={args.get(k)}" for k in sorted(varying_keys)]
            suffix = "_".join(parts)
            simplified = f"{model_name}__{suffix}" if suffix else model_name
            result[simplified] = args

        return result

    def _register_evaluators(self) -> None:
        """Register evaluators from configuration."""
        for evaluator_cfg in self.config.experiment.evaluators:
            evaluator_dict = evaluator_cfg.model_dump()
            evaluator_name = evaluator_dict["name"]
            effective_name = evaluator_dict.get("display_name") or evaluator_name

            if effective_name in self.evaluators_registry:
                raise ValueError(f"Evaluator '{effective_name}' already registered")

            evaluator_class = EVALUATOR_REGISTRY.get(evaluator_name)
            if not evaluator_class:
                raise ValueError(
                    f"Evaluator '{evaluator_name}' not found in registry. "
                    f"Available: {list(EVALUATOR_REGISTRY.keys())}"
                )

            evaluator_instance = evaluator_class(evaluator_dict, self.execution_context)
            self.evaluators_registry[effective_name] = evaluator_instance

    def load_dataset(
        self, dataset_config: Optional[DatasetConfig] = None, dataset_path: Optional[str] = None
    ) -> BaseDataset:
        """Load dataset from configuration."""
        if dataset_config is None:
            dataset_config = self.config.experiment.dataset
            if dataset_config is None:
                raise ValueError("Dataset configuration required")

        dataset_name = dataset_config.name
        dataset_type = dataset_config.type

        dataset_class = DATASET_REGISTRY.get(dataset_type)
        if not dataset_class:
            raise ValueError(
                f"Dataset type '{dataset_type}' not found in registry. "
                f"Available: {list(DATASET_REGISTRY.keys())}"
            )

        # Prepare dataset config
        config = dataset_config.model_dump()
        if dataset_path is not None:
            config["args"]["data_path"] = dataset_path

        # Flatten args into config
        config.update(config.get("args", {}))

        return dataset_class(config, self.execution_context)

    def evaluate(self, dataset: BaseDataset) -> Dict[str, Any]:
        """Evaluate all models on dataset.

        Args:
            dataset: Dataset to evaluate

        Returns:
            Summary dictionary with results
        """
        self.tracking_backend.on_experiment_started(
            ExperimentStartEvent(
                experiment_name=self.config.experiment.name,
                config=self.config.to_dict(),
            )
        )

        total_models = len(self.targets_registry)
        total_records = len(dataset) * total_models
        failed_records = 0

        max_workers = self.config.experiment.max_workers or 4

        if total_models > 1:
            failed_records = self._evaluate_all_parallel(dataset, max_workers)
        else:
            for model_name, model_data in self.targets_registry.items():
                output_path = self._current_experiment_dir / f"{model_name}_results.jsonl"
                failed = self._evaluate_model(dataset, model_name, model_data, output_path, max_workers)
                failed_records += failed

        # Collect aggregated metrics from all model summaries
        all_aggregated: Dict[str, Any] = {}
        for model_name in self.targets_registry:
            summary_path = self._current_experiment_dir / f"{model_name}_summary.json"
            if summary_path.exists():
                try:
                    model_summary = json.loads(summary_path.read_text())
                    model_agg = model_summary.get("aggregated_evaluators", {})
                    if total_models == 1:
                        all_aggregated = model_agg
                    else:
                        all_aggregated[model_name] = model_agg
                except Exception:
                    pass

        summary = {
            "status": "completed_with_errors" if failed_records > 0 else "completed",
            "output_path": str(self._current_experiment_dir),
            "total_records": total_records,
            "failed_records": failed_records,
            "models_evaluated": total_models,
            "aggregated_evaluators": all_aggregated,
        }

        self.tracking_backend.on_experiment_completed(
            ExperimentCompletedEvent(experiment_name=self.config.experiment.name)
        )
        self.tracking_backend.on_shutdown()

        # Clean up OTel trace capture
        if self._trace_capture is not None:
            self._trace_capture.shutdown()

        # Include tracking info in summary
        tracking_type = type(self.tracking_backend).__name__
        if tracking_type != "NoOpFallbackBackend":
            summary["tracking_backend"] = tracking_type
            if hasattr(self.tracking_backend, "published_urls") and self.tracking_backend.published_urls:
                summary["tracking_urls"] = list(self.tracking_backend.published_urls)

        return summary

    def _evaluate_all_parallel(self, dataset: BaseDataset, max_workers: int) -> int:
        """Evaluate all variants in parallel with a shared multi-bar progress display."""
        import threading

        records = list(dataset)  # materialize once for all variants
        total_failed = 0
        lock = threading.Lock()

        # Prepare per-variant work items
        variant_items = []
        for model_name, model_data in self.targets_registry.items():
            output_path = self._current_experiment_dir / f"{model_name}_results.jsonl"
            variant_items.append((model_name, model_data, output_path))

        try:
            from rich.progress import (
                Progress, SpinnerColumn, BarColumn, TextColumn,
                MofNCompleteColumn, TimeElapsedColumn,
            )

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}", justify="left"),
                BarColumn(bar_width=25),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
            ) as progress:
                # Create a task per variant
                tasks = {}
                for model_name, _, _ in variant_items:
                    tasks[model_name] = progress.add_task(
                        f"  {model_name}", total=len(records)
                    )

                def _run_variant(model_name, model_data, output_path):
                    """Run a single variant, updating its progress task."""
                    nonlocal total_failed
                    model_instance = model_data["model"]
                    model_args = model_data["args"]
                    model_config_name = model_data["config"].name

                    run_name = f"run_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    run_id = self.tracking_backend.start_run(
                        ModelRunStartEvent(run_id=run_name, model_name=model_name)
                    ) or run_name

                    variant_failed = 0
                    try:
                        with ThreadPoolExecutor(max_workers=max_workers) as executor:
                            futures = []
                            for record in records:
                                future = executor.submit(
                                    self._evaluate_record,
                                    record, run_id, model_config_name,
                                    model_name, model_instance, **model_args,
                                )
                                futures.append(future)

                            for future in as_completed(futures):
                                try:
                                    eval_output = future.result()
                                    self._save_result(eval_output, output_path)
                                except Exception:
                                    variant_failed += 1
                                progress.advance(tasks[model_name])

                        aggregated = self._aggregate_and_save_evaluators(output_path, model_name)
                        self.tracking_backend.on_results_analyzed(
                            ResultsAnalyzedEvent(run_id=run_id, metrics=aggregated)
                        )
                        self.tracking_backend.on_artifact_generated(
                            ArtifactGeneratedEvent(run_id=run_id, artifact_path=output_path, artifact_type="jsonl")
                        )
                        summary_path = output_path.parent / f"{model_name}_summary.json"
                        self.tracking_backend.on_artifact_generated(
                            ArtifactGeneratedEvent(run_id=run_id, artifact_path=summary_path, artifact_type="json")
                        )
                        # Defer publishing to after progress display ends
                        completed_runs.append((run_id, model_name))
                    except Exception as e:
                        self.tracking_backend.on_run_completed(
                            ModelRunCompletedEvent(run_id=run_id, status=OperationStatus.FAILED, error=str(e))
                        )
                        variant_failed = len(records)

                    with lock:
                        total_failed += variant_failed

                # Run all variants in parallel threads
                completed_runs: list = []
                threads = []
                for model_name, model_data, output_path in variant_items:
                    t = threading.Thread(
                        target=_run_variant,
                        args=(model_name, model_data, output_path),
                    )
                    t.start()
                    threads.append(t)

                for t in threads:
                    t.join()

            # Publish to tracking AFTER progress display ends (clean console output)
            if completed_runs:
                try:
                    from rich.status import Status
                    from rich.console import Console
                    _con = Console()
                    with Status(
                        f"Publishing {len(completed_runs)} run(s) to Foundry...",
                        console=_con,
                        spinner="dots",
                    ) as status:
                        publish_threads = []
                        for run_id, model_name in completed_runs:
                            t = threading.Thread(
                                target=self.tracking_backend.on_run_completed,
                                args=(ModelRunCompletedEvent(run_id=run_id, status=OperationStatus.SUCCESS),),
                            )
                            t.start()
                            publish_threads.append((t, model_name))
                        for t, _ in publish_threads:
                            t.join()
                    _con.print(f"  [bold green]✓[/bold green] Published {len(completed_runs)} run(s) to Foundry")
                except ImportError:
                    for run_id, model_name in completed_runs:
                        self.tracking_backend.on_run_completed(
                            ModelRunCompletedEvent(run_id=run_id, status=OperationStatus.SUCCESS)
                        )

        except ImportError:
            # No Rich — fall back to sequential
            for model_name, model_data, output_path in variant_items:
                failed = self._evaluate_model(dataset, model_name, model_data, output_path, max_workers)
                total_failed += failed

        return total_failed

    def _evaluate_model(
        self,
        dataset: BaseDataset,
        model_name: str,
        model_data: Dict[str, Any],
        output_path: Path,
        max_workers: int,
    ) -> int:
        """Evaluate a single model on dataset using ThreadPoolExecutor."""
        model_instance = model_data["model"]
        model_args = model_data["args"]
        model_config_name = model_data["config"].name

        run_name = f"run_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Start tracking run — use the full variant name (includes args like prompt=baseline)
        run_id = self.tracking_backend.start_run(
            ModelRunStartEvent(run_id=run_name, model_name=model_name)
        )
        if not run_id:
            run_id = run_name

        failed_count = 0

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for record in dataset:
                    future = executor.submit(
                        self._evaluate_record,
                        record,
                        run_id,
                        model_config_name,
                        model_name,
                        model_instance,
                        **model_args,
                    )
                    futures.append(future)

                total = len(futures)
                failed_count = self._collect_results_with_progress(
                    futures, model_name, total, output_path,
                )

            # Aggregate evaluators
            aggregated_metrics = self._aggregate_and_save_evaluators(output_path, model_name)

            self.tracking_backend.on_results_analyzed(
                ResultsAnalyzedEvent(run_id=run_id, metrics=aggregated_metrics)
            )
            self.tracking_backend.on_artifact_generated(
                ArtifactGeneratedEvent(
                    run_id=run_id,
                    artifact_path=output_path,
                    artifact_type="jsonl",
                )
            )
            summary_path = output_path.parent / f"{model_name}_summary.json"
            self.tracking_backend.on_artifact_generated(
                ArtifactGeneratedEvent(
                    run_id=run_id,
                    artifact_path=summary_path,
                    artifact_type="json",
                )
            )
            self.tracking_backend.on_run_completed(
                ModelRunCompletedEvent(run_id=run_id, status=OperationStatus.SUCCESS)
            )
        except Exception as e:
            self.tracking_backend.on_run_completed(
                ModelRunCompletedEvent(
                    run_id=run_id,
                    status=OperationStatus.FAILED,
                    error=str(e),
                )
            )
            raise

        return failed_count

    def _evaluate_record(
        self,
        record: Dict[str, Any],
        run_id: str,
        model_name: str,
        model_display_name: str,
        model: Any,
        **kwargs: Any,
    ) -> EvaluationOutput:
        """Evaluate a single record."""
        record_id = str(hash(json.dumps(record, sort_keys=True, default=str)))[:12]

        try:
            self.tracking_backend.on_inference_started(
                InferenceStartEvent(run_id=run_id, record_id=record_id, input_data=record)
            )
        except Exception:
            pass  # tracking should never break evaluation

        start_time = time.perf_counter()
        agent_trace = None

        try:
            # Run inference — with OTel trace capture if enabled
            if self._trace_capture is not None:
                model_output, agent_trace = self._trace_capture.wrap_target_call(
                    target_fn=model.infer,
                    record=record,
                    model_name=model_name,
                    record_id=record_id,
                )
            else:
                model_output = model.infer(record)

            response_time_ms = (time.perf_counter() - start_time) * 1000

            # Auto-enrich output with trace data if available.
            # Users just return {"answer": "text"} and the engine automatically
            # adds output_items, tool_calls, tool_definitions from the OTel trace.
            if isinstance(model_output, dict):
                has_trace_data = (
                    agent_trace is not None
                    and (agent_trace.llm_calls or agent_trace.log_events)
                )
                if has_trace_data:
                    # Rich trace available — use it for full structured data
                    if "output_items" not in model_output:
                        model_output["output_items"] = agent_trace.to_conversation_format()
                    if "tool_calls" not in model_output:
                        model_output["tool_calls"] = agent_trace.to_tool_calls_format()
                    if "tool_definitions" not in model_output:
                        tool_defs = _extract_tool_definitions_from_trace(agent_trace)
                        if tool_defs:
                            model_output["tool_definitions"] = tool_defs
                elif "output_items" not in model_output and "answer" in model_output:
                    # No trace data and no output_items — create minimal conversation
                    # from answer text so agent evaluators don't get empty responses
                    answer = model_output["answer"]
                    model_output["output_items"] = [
                        {"role": "assistant", "content": [{"type": "text", "text": str(answer)}]}
                    ]

                # Normalize output_items to OpenAI schema regardless of source
                # (handles MAF contents/function_call → content/tool_call conversion)
                if "output_items" in model_output:
                    model_output["output_items"] = _normalize_output_items(model_output["output_items"])

                # Normalize tool_definitions if they're raw function/FunctionTool objects
                if "tool_definitions" in model_output:
                    model_output["tool_definitions"] = _normalize_tool_definitions(
                        model_output["tool_definitions"]
                    )

            # Create inference output — attach trace data if captured
            inference_output = InferenceOutput(
                output=model_output, model_name=model_name, record=record, args=kwargs
            )
            if agent_trace is not None:
                inference_output.agent_trace = agent_trace

            # Compute evaluators
            evaluators = {}
            for evaluator_name, evaluator_instance in self.evaluators_registry.items():
                try:
                    evaluator_result = evaluator_instance.compute(inference_output)
                    evaluators[evaluator_name] = evaluator_result
                except Exception:
                    evaluators[evaluator_name] = {"error": "computation_failed"}

            # Emit OTel evaluation result events for each evaluator score
            if agent_trace is not None and self._trace_capture is not None:
                for eval_name, eval_result in evaluators.items():
                    if isinstance(eval_result, dict) and "error" not in eval_result:
                        score_val = None
                        score_label = None
                        explanation = None
                        for k, v in eval_result.items():
                            if isinstance(v, (int, float)):
                                score_val = float(v)
                            elif isinstance(v, str) and k in ("label", "result"):
                                score_label = v
                            elif isinstance(v, str) and k in ("reason", "explanation"):
                                explanation = v
                        self._trace_capture.emit_evaluation_result(
                            trace_id=agent_trace.trace_id,
                            span_id=agent_trace.parent_span_id,
                            evaluator_name=eval_name,
                            score_value=score_val,
                            score_label=score_label,
                            explanation=explanation,
                        )

            system_metrics = {"response_time": {"response_time_ms": response_time_ms}}
            # Include trace metrics in system metrics if available
            if agent_trace is not None:
                system_metrics["trace"] = {
                    "llm_call_count": len(agent_trace.llm_calls),
                    "total_input_tokens": agent_trace.total_input_tokens,
                    "total_output_tokens": agent_trace.total_output_tokens,
                    "total_llm_duration_ms": agent_trace.total_duration_ms,
                    "tool_call_count": len(agent_trace.tool_calls),
                }

            try:
                self.tracking_backend.on_inference_completed(
                    InferenceCompletedEvent(
                        run_id=run_id,
                        record_id=record_id,
                        output_data={"output": model_output, "evaluators": evaluators},
                        duration_ms=response_time_ms,
                        status=OperationStatus.SUCCESS,
                    )
                )
            except Exception:
                pass  # tracking should never break evaluation

            return EvaluationOutput(
                run_id=run_id,
                inference_output=inference_output,
                evaluators=evaluators,
                system_evaluators=system_metrics,
                model_display_name=model_display_name,
                metadata={},
            )
        except Exception as e:
            try:
                self.tracking_backend.on_inference_completed(
                    InferenceCompletedEvent(
                        run_id=run_id,
                        record_id=record_id,
                        output_data={"error": str(e)},
                        duration_ms=(time.perf_counter() - start_time) * 1000,
                        status=OperationStatus.FAILED,
                    )
                )
            except Exception:
                pass  # tracking should never break evaluation
            raise

    def _collect_results_with_progress(
        self,
        futures: list,
        model_name: str,
        total: int,
        output_path: Path,
    ) -> int:
        """Collect futures showing a Rich progress bar when available."""
        failed_count = 0
        try:
            from rich.progress import (
                Progress,
                SpinnerColumn,
                BarColumn,
                TextColumn,
                MofNCompleteColumn,
                TimeElapsedColumn,
            )

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(bar_width=30),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
            ) as progress:
                task = progress.add_task(f"Evaluating {model_name}", total=total)
                for future in as_completed(futures):
                    try:
                        eval_output = future.result()
                        self._save_result(eval_output, output_path)
                    except Exception:
                        failed_count += 1
                    progress.advance(task)
        except ImportError:
            for future in as_completed(futures):
                try:
                    eval_output = future.result()
                    self._save_result(eval_output, output_path)
                except Exception:
                    failed_count += 1
        return failed_count

    def _save_result(self, eval_output: EvaluationOutput, output_path: Path) -> None:
        """Save evaluation result to JSONL file."""
        with open(output_path, "a") as f:
            f.write(json.dumps(eval_output.to_dict()) + "\n")

    def _aggregate_and_save_evaluators(self, results_path: Path, model_name: str) -> Dict[str, Any]:
        """Aggregate evaluator results and save summary.

        Returns:
            Aggregated evaluators dictionary.
        """
        if not results_path.exists():
            return {}

        # Load all results
        results = []
        with open(results_path) as f:
            for line in f:
                results.append(json.loads(line))

        # Aggregate evaluators
        aggregated: Dict[str, Any] = {}
        for evaluator_name, evaluator_instance in self.evaluators_registry.items():
            scores = [r.get("evaluators", r.get("metrics", {})).get(evaluator_name, {}) for r in results]
            scores = [s for s in scores if "error" not in s]  # Filter errors

            if scores:
                try:
                    aggregated[evaluator_name] = evaluator_instance.aggregate(scores)
                except Exception:
                    aggregated[evaluator_name] = {"error": "aggregation_failed"}

        # Save summary
        summary = {"model": model_name, "total_records": len(results), "aggregated_evaluators": aggregated, "aggregated_metrics": aggregated}

        summary_path = results_path.parent / f"{model_name}_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        return aggregated
