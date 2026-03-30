"""Model evaluator for running experiments."""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config, DatasetConfig, EvaluatorConfig, TargetVariantConfig
from .dataset_factory import DatasetFactory
from .decorators import DATASET_REGISTRY, EVALUATOR_REGISTRY, TARGET_REGISTRY, BaseDataset, BaseTarget as EveeBaseTarget
from .discovery import discover_components
from .logging import setup_logger as _setup_logger
from .metrics_aggregator import MetricsAggregator
from .models import EvaluationOutput, ExecutionContext, InferenceOutput
from .otel_trace_capture import OTelTraceCapture
from .progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)

OUTPUT_PATH_OVERRIDE_ENV = "EV_OUTPUT_PATH_OVERRIDE"
AITK_JOBS_DIR_ENV = "AITK_EVALS_JOBS_DIR"


def _extract_tool_definitions_from_trace(agent_trace) -> list:
    """Extract tool definitions from OTel trace spans.

    Checks multiple sources in priority order:
    1. gen_ai.tool.definitions (MAF / standard semconv)
    2. gen_ai.request.tools (azure-ai-projects ResponsesInstrumentor)
    3. Inferred from tool calls in the conversation (fallback, same as RAISvc cloud)
    """
    import json as _json

    # Try explicit tool definitions from span attributes
    for attr_name in ("gen_ai.tool.definitions", "gen_ai.request.tools"):
        for span in agent_trace.spans:
            tool_defs = span.attributes.get(attr_name)
            if not tool_defs:
                continue

            if isinstance(tool_defs, str):
                try:
                    parsed = _json.loads(tool_defs)
                except (_json.JSONDecodeError, ValueError):
                    continue
            elif isinstance(tool_defs, (list, tuple)):
                parsed = list(tool_defs)
            else:
                continue

            # Flatten nested OpenAI format if needed
            result = []
            for td in parsed:
                if isinstance(td, dict) and "function" in td and isinstance(td["function"], dict):
                    flat = {"type": td.get("type", "function")}
                    flat.update(td["function"])
                    result.append(flat)
                elif isinstance(td, dict):
                    result.append(td)
            if result:
                return result

    # Fallback: infer tool definitions from tool calls in the trace
    # (same approach as RAISvc cloud evaluation)
    return _infer_tool_definitions_from_trace(agent_trace)


def _infer_tool_definitions_from_trace(agent_trace) -> list:
    """Infer tool definitions from tool calls found in the trace.

    When gen_ai.tool.definitions is not available, we can derive basic tool
    definitions from the tool calls themselves (names + argument types).
    This matches what the RAISvc cloud evaluation does as a fallback.
    """
    import json as _json

    inferred: dict = {}

    # From execute_tool spans
    for span in agent_trace.spans:
        if span.operation_name == "execute_tool":
            name = span.attributes.get("gen_ai.tool.name", "")
            if name and name not in inferred:
                args_raw = span.attributes.get("gen_ai.tool.call.arguments", {})
                if isinstance(args_raw, str):
                    try:
                        args_raw = _json.loads(args_raw)
                    except (_json.JSONDecodeError, ValueError):
                        args_raw = {}

                # Build parameter schema from argument values
                props = {}
                if isinstance(args_raw, dict):
                    for k, v in args_raw.items():
                        if isinstance(v, str):
                            props[k] = {"type": "string"}
                        elif isinstance(v, bool):
                            props[k] = {"type": "boolean"}
                        elif isinstance(v, int):
                            props[k] = {"type": "integer"}
                        elif isinstance(v, float):
                            props[k] = {"type": "number"}
                        else:
                            props[k] = {"type": "string"}

                inferred[name] = {
                    "name": name,
                    "type": "function",
                    "description": span.attributes.get("gen_ai.tool.description", name),
                    "parameters": {"type": "object", "properties": props},
                }

    # From tool_calls in the trace
    for tc in agent_trace.tool_calls:
        name = tc.get("name", "")
        if name and name not in inferred:
            args = tc.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = _json.loads(args)
                except (_json.JSONDecodeError, ValueError):
                    args = {}

            props = {}
            if isinstance(args, dict):
                for k, v in args.items():
                    if isinstance(v, str):
                        props[k] = {"type": "string"}
                    elif isinstance(v, bool):
                        props[k] = {"type": "boolean"}
                    elif isinstance(v, int):
                        props[k] = {"type": "integer"}
                    elif isinstance(v, float):
                        props[k] = {"type": "number"}
                    else:
                        props[k] = {"type": "string"}

            inferred[name] = {
                "name": name,
                "type": "function",
                "description": name,
                "parameters": {"type": "object", "properties": props},
            }

    return list(inferred.values())


class ModelEvaluator:
    """Main evaluator for assessing AI models."""

    def __init__(
        self,
        config_path: str = "config.yaml",
        load_config_only: bool = False,
        model_filter: Optional[List[str]] = None,
    ) -> None:
        """Initialize evaluator.

        Args:
            config_path: Path to configuration YAML file
            load_config_only: Whether to only load configuration
            model_filter: Optional list of model names to evaluate
        """
        self.model_filter = model_filter
        self._config_path = str(Path(config_path).resolve())

        # Auto-discover components
        discover_components()

        # Load config
        self.config = Config.from_yaml(config_path)

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

        # Set up structured logging with file handler in experiment directory
        _setup_logger(__name__, logs_path=str(self._current_experiment_dir))

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

        output_base = self.config.experiment.output_path
        output_override = (os.environ.get(OUTPUT_PATH_OVERRIDE_ENV) or "").strip()
        if output_override:
            output_base = output_override

        output_path = self._current_dir / output_base / exp_dir
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
        connections_registry = self.connections_registry

        # Resolve project endpoint: connection → target config → compute → tracking
        project_endpoint = getattr(target_cfg, "azure_ai_project", None)
        if not project_endpoint:
            conn_name = getattr(target_cfg, "connection_name", None) or "default"
            conn = connections_registry.get(conn_name)
            if conn:
                if hasattr(conn, "model_dump"):
                    conn = conn.model_dump()
                project_endpoint = conn.get("azure_ai_project")
        if not project_endpoint and self.config.experiment.compute:
            project_endpoint = getattr(self.config.experiment.compute, "azure_ai_project", None)

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

    def _register_target(self, target_cfg: TargetVariantConfig) -> None:
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
        """Create a passthrough target that returns dataset record as output."""
        from .decorators import BaseTarget

        class PassthroughTarget(BaseTarget):
            def __init__(self, config: Optional[Dict[str, Any]] = None, context: Optional[Any] = None):
                super().__init__(context)

            def infer(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
                return input_data

        PassthroughTarget.__name__ = name
        return PassthroughTarget

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
        # Ensure all SDK evaluators with evee integration blocks are imported
        # so their @evaluator decorators register them in EVALUATOR_REGISTRY.
        try:
            from azure.ai.evaluation._evaluators._coherence._coherence import CoherenceEvaluator  # noqa: F401
            from azure.ai.evaluation._evaluators._f1_score._f1_score import F1ScoreEvaluator  # noqa: F401
            from azure.ai.evaluation._evaluators._relevance._relevance import RelevanceEvaluator  # noqa: F401
            from azure.ai.evaluation._evaluators._task_adherence._task_adherence import TaskAdherenceEvaluator  # noqa: F401
            from azure.ai.evaluation._evaluators._intent_resolution._intent_resolution import IntentResolutionEvaluator  # noqa: F401
            from azure.ai.evaluation._evaluators._tool_call_accuracy._tool_call_accuracy import ToolCallAccuracyEvaluator  # noqa: F401
            from azure.ai.evaluation._evaluators._tool_call_success._tool_call_success import _ToolCallSuccessEvaluator  # noqa: F401
            from azure.ai.evaluation._evaluators._tool_selection._tool_selection import _ToolSelectionEvaluator  # noqa: F401
            from azure.ai.evaluation._evaluators._tool_input_accuracy._tool_input_accuracy import _ToolInputAccuracyEvaluator  # noqa: F401
            from azure.ai.evaluation._evaluators._tool_output_utilization._tool_output_utilization import _ToolOutputUtilizationEvaluator  # noqa: F401
            from azure.ai.evaluation._evaluators._task_completion._task_completion import _TaskCompletionEvaluator  # noqa: F401
        except ImportError:
            pass  # Some evaluators may not be available

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
        """Load dataset from configuration.

        Uses :class:`DatasetFactory` for type routing and path overrides.
        """
        if dataset_config is None:
            dataset_config = self.config.experiment.dataset
            if dataset_config is None:
                raise ValueError("Dataset configuration required")

        factory = DatasetFactory()
        return factory.create_from_config(
            dataset_config,
            dataset_path_override=dataset_path,
            context=self.execution_context,
        )

    def evaluate(self, dataset: BaseDataset) -> Dict[str, Any]:
        """Evaluate all models on dataset.

        Args:
            dataset: Dataset to evaluate

        Returns:
            Summary dictionary with results
        """
        # Suppress noisy non-fatal warnings from SDK evaluators and LangChain callbacks
        for _logger_name in ("langchain_core.callbacks.manager", "langchain_core.callbacks", "langchain_azure_ai"):
            logging.getLogger(_logger_name).setLevel(logging.ERROR)

        total_models = len(self.targets_registry)
        total_records = len(dataset) * total_models
        failed_records = 0
        first_error_msg = None

        max_workers = self.config.experiment.max_workers or 4

        if total_models > 1:
            failed_records, first_error_msg = self._evaluate_all_parallel(dataset, max_workers)
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
        if first_error_msg:
            summary["first_error"] = first_error_msg

        aitk_job_path = self._persist_aitk_job_artifacts()
        if aitk_job_path is not None:
            summary["aitk_job_path"] = str(aitk_job_path)

        sidebar_path = self._persist_aitk_sidebar_results()
        if sidebar_path is not None:
            summary["aitk_sidebar_path"] = str(sidebar_path)

        # Clean up OTel trace capture
        if self._trace_capture is not None:
            self._trace_capture.shutdown()

        return summary

    def _persist_aitk_sidebar_results(self) -> Optional[Path]:
        """Write a flat rows JSON to <workspace>/test-results/ for the AITK sidebar tree.

        The AI Toolkit extension's "View Local Evaluation Results" tree node scans
        <vscode_workspace>/test-results/**/*.json and shows each file.  Clicking a
        file opens it in the Data Viewer.  The Data Viewer auto-selects a root-level
        array, so we write just the rows array as the JSON root to give the user an
        immediate tabular view of inputs/outputs.
        """
        try:
            consolidated_results = self._build_consolidated_results_payload()
            if not consolidated_results:
                return None
            rows = consolidated_results.get("rows") or []
            if not rows:
                return None

            # Determine where the VS Code workspace root is.  When ev run is invoked
            # from the project directory, cwd == workspace root.
            workspace_root = self._current_dir
            test_results_dir = workspace_root / "test-results"
            test_results_dir.mkdir(parents=True, exist_ok=True)

            # Use the experiment directory name as the filename so the Data Viewer
            # shows a descriptive label.
            filename = f"{self._current_experiment_dir.name}.json"
            output_file = test_results_dir / filename
            # Write just the rows array at the root so the Data Viewer opens it
            # as a table immediately without requiring a property selection step.
            output_file.write_text(json.dumps(rows, indent=2), encoding="utf-8")

            logger.debug("Wrote AITK sidebar results to %s", output_file)
            return output_file
        except Exception:
            logger.exception("Failed to persist AITK sidebar results")
            return None

    def _persist_aitk_job_artifacts(self) -> Optional[Path]:
        """Copy evaluate-style artifacts into AI Toolkit jobs folder.

        The Evaluation pane consumes per-job artifacts from ~/.aitk/evals/jobs.
        This writes a consolidated results.json plus lightweight metadata there
        for discovery.
        """
        consolidated_results = self._build_consolidated_results_payload()
        if consolidated_results is None:
            return None

        try:
            configured_root = (os.environ.get(AITK_JOBS_DIR_ENV) or "").strip()
            jobs_root = Path(configured_root) if configured_root else (Path.home() / ".aitk" / "evals" / "jobs")
            job_dir = jobs_root / self._current_experiment_dir.name
            job_dir.mkdir(parents=True, exist_ok=True)

            created_at = datetime.now().isoformat()

            results_file = job_dir / "results.json"
            results_file.write_text(json.dumps(consolidated_results, indent=2), encoding="utf-8")

            # Resolve dataset path for the input contract
            dataset_cfg = self.config.experiment.dataset
            raw_path = (
                getattr(dataset_cfg, "path", None)
                or (getattr(dataset_cfg, "args", None) or {}).get("data_path", "")
                or ""
            )
            # Resolve relative paths against cwd so the extension can open the file
            dataset_path = str(
                (self._current_dir / raw_path).resolve() if raw_path and not Path(raw_path).is_absolute() else Path(raw_path).resolve() if raw_path else ""
            )

            # Collect evaluator names
            evaluator_names = [
                (getattr(ev, "display_name", None) or getattr(ev, "name", ""))
                for ev in (self.config.experiment.evaluators or [])
            ]

            # The extension's parseJobMetadata requires: id, input, status
            metadata = {
                "id": self._current_experiment_dir.name,
                "input": {
                    "evalName": self.config.experiment.name,
                    "dataset": {"path": dataset_path},
                    "evaluators": evaluator_names,
                    "evalConfigFilePath": self._config_path,
                },
                "status": "completed",
                "createTime": created_at,
                "evalResultFilePath": str(results_file),
            }
            (job_dir / "job-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

            log_file = self._current_experiment_dir / "model_evaluation.log"
            if log_file.exists():
                shutil.copy2(log_file, job_dir / "logs.txt")
            else:
                (job_dir / "logs.txt").write_text("", encoding="utf-8")

            logger.debug("Copied AI Toolkit job artifacts to %s", job_dir)
            return job_dir
        except Exception:
            logger.exception("Failed to persist AI Toolkit job artifacts")
            return None

    def _build_consolidated_results_payload(self) -> Optional[Dict[str, Any]]:
        """Build evaluate()-style results payload for extension ingestion.

        Shape matches the common local artifact contract used by the Evaluation UI:
        {
            "evaluation_id": ..., "run_id": ..., "status": ..., "metrics": {...},
            "rows": [...], "report_url": null, "studio_url": null
        }
        """
        summary_files = sorted(self._current_experiment_dir.glob("*_summary.json"))
        result_files = sorted(self._current_experiment_dir.glob("*_results.jsonl"))
        if not summary_files and not result_files:
            return None

        metrics: Dict[str, Any] = {}
        for summary_file in summary_files:
            model_name = summary_file.stem.replace("_summary", "")
            try:
                summary_data = json.loads(summary_file.read_text())
            except Exception:
                continue

            aggregated = summary_data.get("aggregated_evaluators") or summary_data.get("aggregated_metrics") or {}
            if not isinstance(aggregated, dict):
                continue

            for evaluator_name, evaluator_value in aggregated.items():
                if isinstance(evaluator_value, dict):
                    for key, value in evaluator_value.items():
                        if isinstance(value, (int, float)):
                            metrics[f"{model_name}.{evaluator_name}.{key}"] = value
                elif isinstance(evaluator_value, (int, float)):
                    metrics[f"{model_name}.{evaluator_name}"] = evaluator_value

        rows: List[Dict[str, Any]] = []
        for results_file in result_files:
            model_name = results_file.stem.replace("_results", "")
            with open(results_file, "r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    row: Dict[str, Any] = {"outputs.model_name": item.get("model_display_name") or model_name}

                    record = item.get("record")
                    if isinstance(record, dict):
                        for key, value in record.items():
                            row[f"inputs.{key}"] = value

                    output = item.get("output")
                    if isinstance(output, dict):
                        if "response" in output:
                            row["outputs.response"] = output.get("response")
                        elif "answer" in output:
                            row["outputs.response"] = output.get("answer")

                    evaluators = item.get("evaluators") or item.get("metrics") or {}
                    if isinstance(evaluators, dict):
                        for evaluator_name, evaluator_data in evaluators.items():
                            if isinstance(evaluator_data, dict):
                                for metric_name, metric_value in evaluator_data.items():
                                    row[f"outputs.{evaluator_name}.{metric_name}"] = metric_value

                    rows.append(row)

        run_id = self._current_experiment_dir.name
        return {
            "evaluation_id": run_id,
            "run_id": run_id,
            "status": "completed",
            "rows": rows,
            "metrics": metrics,
            "report_url": None,
            "studio_url": None,
            # Compatibility aliases for consumers that expect camelCase keys.
            "evaluationId": run_id,
            "runId": run_id,
            "reportUrl": None,
            "studioUrl": None,
        }

    def _evaluate_all_parallel(self, dataset: BaseDataset, max_workers: int) -> int:
        """Evaluate all variants in parallel with a shared multi-bar progress display."""
        import threading

        records = list(dataset)  # materialize once for all variants
        total_failed = 0
        first_error = None
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
                    nonlocal total_failed, first_error
                    model_instance = model_data["model"]
                    model_args = model_data["args"]
                    model_config_name = model_data["config"].name

                    run_name = f"run_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    run_id = run_name

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
                                except Exception as e:
                                    variant_failed += 1
                                    logger.error("Record evaluation failed: %s", e)
                                    with lock:
                                        if first_error is None:
                                            first_error = str(e)
                                progress.advance(tasks[model_name])

                        self._aggregate_and_save_evaluators(output_path, model_name)
                    except Exception as e:
                        variant_failed = len(records)
                        logger.error("Variant '%s' failed: %s", model_name, e)
                        with lock:
                            if first_error is None:
                                first_error = str(e)

                    with lock:
                        total_failed += variant_failed

                # Run all variants in parallel threads
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

        except ImportError:
            # No Rich — fall back to sequential
            for model_name, model_data, output_path in variant_items:
                failed = self._evaluate_model(dataset, model_name, model_data, output_path, max_workers)
                total_failed += failed

        return total_failed, first_error

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
            self._aggregate_and_save_evaluators(output_path, model_name)

        except Exception:
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

            # Auto-enrich output from OTel traces.
            # Targets just return {"answer": text} — everything else comes from traces.
            if isinstance(model_output, dict):
                has_trace_data = (
                    agent_trace is not None
                    and (agent_trace.llm_calls or agent_trace.log_events)
                )
                if has_trace_data:
                    if "output_items" not in model_output:
                        model_output["output_items"] = agent_trace.to_conversation_format()
                    if "tool_calls" not in model_output:
                        model_output["tool_calls"] = agent_trace.to_tool_calls_format()
                    if "tool_definitions" not in model_output:
                        tool_defs = _extract_tool_definitions_from_trace(agent_trace)
                        if tool_defs:
                            model_output["tool_definitions"] = tool_defs

                # Fallback: infer tool definitions from tool_calls if still missing
                # (covers cases where OTel doesn't capture gen_ai.request.tools)
                if "tool_definitions" not in model_output and model_output.get("tool_calls"):
                    inferred = _infer_tool_definitions_from_trace(agent_trace) if agent_trace else []
                    if not inferred:
                        # Infer from model_output["tool_calls"] directly
                        seen = {}
                        for tc in model_output["tool_calls"]:
                            name = tc.get("name", "")
                            if name and name not in seen:
                                args = tc.get("arguments", {})
                                props = {k: {"type": "string"} for k in args} if isinstance(args, dict) else {}
                                seen[name] = {
                                    "type": "function", "name": name, "description": name,
                                    "parameters": {"type": "object", "properties": props},
                                }
                        inferred = list(seen.values())
                    if inferred:
                        model_output["tool_definitions"] = inferred

                # Fallback: minimal output_items from response/answer text
                _response_text = model_output.get("response") or model_output.get("answer")
                if "output_items" not in model_output and _response_text:
                    model_output["output_items"] = [
                        {"role": "assistant", "content": [{"type": "text", "text": str(_response_text)}]}
                    ]

                # Prepend user query for evaluator conversation parser
                if "output_items" in model_output:
                    items = model_output["output_items"]
                    if items and items[0].get("role") != "user":
                        query_text = record.get("query") or record.get("question") or record.get("prompt") or ""
                        if query_text:
                            items.insert(0, {"role": "user", "content": str(query_text)})

                    # Ensure the final text answer is in output_items
                    # (OTel may miss the last response due to timing)
                    answer = model_output.get("response") or model_output.get("answer", "")
                    if answer and items:
                        last = items[-1]
                        last_has_text = (
                            last.get("role") == "assistant"
                            and isinstance(last.get("content"), list)
                            and any(isinstance(c, dict) and c.get("type") == "text" for c in last["content"])
                        )
                        if not last_has_text:
                            items.append({"role": "assistant", "content": [{"type": "text", "text": str(answer)}]})

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
                except Exception as eval_err:
                    evaluators[evaluator_name] = {"error": f"computation_failed: {eval_err}"}

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

            return EvaluationOutput(
                run_id=run_id,
                inference_output=inference_output,
                evaluators=evaluators,
                system_evaluators=system_metrics,
                model_display_name=model_display_name,
                metadata={},
            )
        except Exception as e:
            raise

    def _collect_results_with_progress(
        self,
        futures: list,
        model_name: str,
        total: int,
        output_path: Path,
    ) -> int:
        """Collect futures showing a progress bar (Rich when available, logging fallback)."""
        failed_count = 0
        with ProgressTracker(total_targets=1) as tracker:
            tracker.begin_target(model_name, total_records=total)
            for future in as_completed(futures):
                try:
                    eval_output = future.result()
                    self._save_result(eval_output, output_path)
                except Exception as e:
                    failed_count += 1
                    logger.error("Record evaluation failed: %s", e)
                tracker.advance()
            tracker.finish_target()
        return failed_count

    def _save_result(self, eval_output: EvaluationOutput, output_path: Path) -> None:
        """Save evaluation result to JSONL file."""
        with open(output_path, "a") as f:
            f.write(json.dumps(eval_output.to_dict()) + "\n")

    def _aggregate_and_save_evaluators(self, results_path: Path, model_name: str) -> Dict[str, Any]:
        """Aggregate evaluator results and save summary.

        Uses :class:`MetricsAggregator` for the core aggregation logic.

        Returns:
            Aggregated evaluators dictionary.
        """
        if not results_path.exists():
            return {}

        aggregator = MetricsAggregator(self.evaluators_registry)
        analysis = aggregator.analyze_results(results_path)

        # Reconstruct per-evaluator breakdown from prefixed metrics
        aggregated: Dict[str, Any] = {}
        for evaluator_name in self.evaluators_registry:
            prefix = f"{evaluator_name} - "
            evaluator_values: Dict[str, Any] = {}
            for key, value in analysis.aggregated_metrics.items():
                if key.startswith(prefix):
                    short_key = key[len(prefix):]
                    if short_key == "Aggregation Failed":
                        evaluator_values = {"error": "aggregation_failed"}
                        break
                    evaluator_values[short_key] = value
            if evaluator_values:
                aggregated[evaluator_name] = evaluator_values

        # Save summary
        total_records = analysis.aggregated_metrics.get("number_of_records", 0)
        summary = {
            "model": model_name,
            "total_records": total_records,
            "aggregated_evaluators": aggregated,
            "aggregated_metrics": aggregated,
        }

        summary_path = results_path.parent / f"{model_name}_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        return aggregated
