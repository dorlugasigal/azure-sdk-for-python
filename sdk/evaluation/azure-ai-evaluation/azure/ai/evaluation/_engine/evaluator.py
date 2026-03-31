"""Model evaluator for running experiments."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config, DatasetConfig
from .dataset_factory import DatasetFactory
from .decorators import EVALUATOR_REGISTRY, BaseDataset
from .discovery import discover_components
from .evaluation_executor import EvaluationExecutor
from .logging import setup_logger as _setup_logger
from .models import ExecutionContext
from .otel_trace_capture import OTelTraceCapture
from .output_formatter import OutputFormatter
from .target_factory import TargetFactory

logger = logging.getLogger(__name__)

OUTPUT_PATH_OVERRIDE_ENV = "EV_OUTPUT_PATH_OVERRIDE"


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


def _apply_target_input_mapping(
    record: Dict[str, Any], mapping: Dict[str, str]
) -> Dict[str, Any]:
    """Apply target input mapping: build mapped input from dataset fields.

    For each mapping entry with a ``dataset.X`` source, the dataset field ``X``
    is copied into the result under the mapping key.  Fields not covered by the
    mapping are passed through unchanged so that existing targets continue to
    work when only a partial mapping is specified.
    """
    if not mapping:
        return record

    input_mapping = {
        param: source_field.split(".", 1)[1]
        for param, source_field in mapping.items()
        if source_field.startswith("dataset.")
    }
    if not input_mapping:
        return record

    mapped: Dict[str, Any] = {}
    for param, dataset_field in input_mapping.items():
        if dataset_field not in record:
            raise KeyError(
                f"Target input mapping: field '{dataset_field}' not found in dataset record. "
                f"Available fields: {list(record.keys())}"
            )
        mapped[param] = record[dataset_field]

    # Pass through unmapped fields so targets that read extra columns still work
    for key, value in record.items():
        if key not in mapped:
            mapped[key] = value

    return mapped


def _apply_target_output_mapping(
    model_output: Dict[str, Any], mapping: Dict[str, str]
) -> Dict[str, Any]:
    """Apply target output mapping: rename target output keys to canonical names.

    For each mapping entry with a ``target.X`` source, the target output field
    ``X`` is renamed to the mapping key (the canonical name the engine expects,
    e.g. ``response``).
    """
    if not mapping or not isinstance(model_output, dict):
        return model_output

    output_mapping = {
        canonical: source_field.split(".", 1)[1]
        for canonical, source_field in mapping.items()
        if source_field.startswith("target.")
    }
    if not output_mapping:
        return model_output

    result = dict(model_output)
    for canonical, target_field in output_mapping.items():
        if target_field in result:
            value = result.pop(target_field)
            result[canonical] = value

    return result


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

        # Output formatter for AITK persistence and result building
        self._output = OutputFormatter(
            current_dir=self._current_dir,
            experiment_dir=self._current_experiment_dir,
            config_path=self._config_path,
            experiment_name=self.config.experiment.name,
            dataset_config=self.config.experiment.dataset,
            evaluator_configs=self.config.experiment.evaluators,
        )

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

        self._target_factory = TargetFactory(
            config=self.config,
            execution_context=self.execution_context,
            connections_registry=self.connections_registry,
        )
        self.targets_registry = self._target_factory.register_targets(model_filter)
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

        executor = EvaluationExecutor(
            evaluators_registry=self.evaluators_registry,
            trace_capture=self._trace_capture,
            experiment_dir=self._current_experiment_dir,
        )
        self._executor = executor

        if total_models > 1:
            failed_records, first_error_msg = executor.evaluate_all_parallel(
                self.targets_registry, dataset, max_workers,
            )
        else:
            for model_name, model_data in self.targets_registry.items():
                output_path = self._current_experiment_dir / f"{model_name}_results.jsonl"
                failed = executor.evaluate_model(dataset, model_name, model_data, output_path, max_workers)
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

        aitk_job_path = self._output.persist_aitk_job_artifacts()
        if aitk_job_path is not None:
            summary["aitk_job_path"] = str(aitk_job_path)

        sidebar_path = self._output.persist_aitk_sidebar_results()
        if sidebar_path is not None:
            summary["aitk_sidebar_path"] = str(sidebar_path)

        # Clean up OTel trace capture
        if self._trace_capture is not None:
            self._trace_capture.shutdown()

        return summary
