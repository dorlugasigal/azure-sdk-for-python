"""Model evaluator for running experiments."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.config import Config, ConnectionConfig, DatasetConfig
from ..dataset_factory import DatasetFactory
from ..decorators import EVALUATOR_REGISTRY, BaseDataset
from ..discovery import discover_components
from .evaluation_executor import EvaluationExecutor
from ..logging import setup_logger as _setup_logger
from ..models.execution_context import ExecutionContext
from ..tracing.otel_trace_capture import OTelTraceCapture
from .output_formatter import OutputFormatter
from ..targets.target_factory import TargetFactory
from ..targets.target_mapping import _apply_target_input_mapping
from ..tracing.trace_utils import _extract_tool_definitions_from_trace, _infer_tool_definitions_from_trace

# Re-export so that existing ``from .evaluator import …`` statements keep working.
__all__ = [
    "ModelEvaluator",
    "_apply_target_input_mapping",
    "_extract_tool_definitions_from_trace",
    "_infer_tool_definitions_from_trace",
]

logger = logging.getLogger(__name__)

OUTPUT_PATH_OVERRIDE_ENV = "EV_OUTPUT_PATH_OVERRIDE"


class ModelEvaluator:
    """Main evaluator for assessing AI models."""

    def __init__(
        self,
        config_path: str = "config.yaml",
        load_config_only: bool = False,
        model_filter: Optional[List[str]] = None,
    ) -> None:
        """Initialize evaluator.

        :param config_path: Path to the configuration YAML file.
        :type config_path: str
        :param load_config_only: When ``True``, only load the configuration without
            setting up experiment infrastructure.
        :type load_config_only: bool
        :param model_filter: Optional list of model names to limit evaluation to.
        :type model_filter: list[str] or None
        """
        self.model_filter = model_filter
        self._config_path = str(Path(config_path).resolve())

        logger.debug("Discovering components...")
        discover_components()
        logger.debug("Component discovery complete")

        logger.info("Loading configuration from %s", config_path)
        self.config = Config.from_yaml(config_path)
        logger.debug("Configuration loaded successfully")

        if load_config_only:
            self._trace_capture = self._setup_tracing()
            return

        self._current_dir = Path.cwd()
        self._current_experiment_dir = self._create_experiment_dir()
        self._setup_logging()
        logger.info("Experiment directory: %s", self._current_experiment_dir)

        self._trace_capture = self._setup_tracing()
        self._output = self._setup_output_formatter()

        logger.debug("Initializing connections registry")
        self.connections_registry = self._build_connections_registry()
        if not self.connections_registry:
            logger.warning("No connections found in configuration. Proceeding without connections.")
        else:
            logger.debug("Registered %d connection(s)", len(self.connections_registry))

        self.execution_context = self._build_execution_context()

        logger.debug("Registering targets")
        self.targets_registry = self._register_targets(model_filter)
        logger.info("Registered %d target(s): %s", len(self.targets_registry), list(self.targets_registry.keys()))

        self.evaluators_registry: Dict[str, Any] = {}
        self._register_evaluators()
        logger.info("Registered %d evaluator(s): %s", len(self.evaluators_registry), list(self.evaluators_registry.keys()))

    # ------------------------------------------------------------------
    # __init__ helpers
    # ------------------------------------------------------------------

    def _setup_tracing(self) -> Optional[OTelTraceCapture]:
        """Set up OTel trace capture if the SDK is available.

        :returns: An initialised :class:`OTelTraceCapture` or ``None``.
        :rtype: OTelTraceCapture or None
        """
        trace_capture = OTelTraceCapture(capture_content=True)
        if trace_capture.setup():
            return trace_capture
        return None

    def _setup_logging(self) -> None:
        """Configure structured logging with a file handler in the experiment directory.

        Sets up the ``azure.ai.evaluation._engine`` parent logger so that
        every sub-module under ``_engine`` automatically gets file + console
        logging via propagation — matching the original evee project where
        each component called ``setup_logger()`` individually.
        """
        _ENGINE_LOGGER_NAME = "azure.ai.evaluation._engine"
        _setup_logger(
            _ENGINE_LOGGER_NAME,
            logs_path=str(self._current_experiment_dir),
            force=True,
        )
        self._logger = logging.getLogger(__name__)

    def _setup_output_formatter(self) -> OutputFormatter:
        """Build the :class:`OutputFormatter` for AITK persistence and result building.

        :returns: A configured :class:`OutputFormatter` instance.
        :rtype: OutputFormatter
        """
        return OutputFormatter(
            current_dir=self._current_dir,
            experiment_dir=self._current_experiment_dir,
            config_path=self._config_path,
            experiment_name=self.config.experiment.name,
            dataset_config=self.config.experiment.dataset,
            evaluator_configs=self.config.experiment.evaluators,
        )

    def _build_connections_registry(self) -> Dict[str, Any]:
        """Build a registry of configured connections.

        :returns: A dictionary mapping connection names to their configuration objects.
        :rtype: dict[str, Any]
        """
        registry: Dict[str, Any] = {}
        connections = self.config.experiment.connections
        if isinstance(connections, list):
            for connection in connections:
                if hasattr(connection, "name"):
                    registry[connection.name] = connection
                elif isinstance(connection, dict):
                    name = connection.get("name", "default")
                    registry[name] = ConnectionConfig(**connection)
        return registry

    def _build_execution_context(self) -> ExecutionContext:
        """Create the :class:`ExecutionContext` for this experiment run.

        :returns: A populated :class:`ExecutionContext`.
        :rtype: ExecutionContext
        """
        return ExecutionContext(
            connections_registry=self.connections_registry,
            cloud_config=self.config.experiment.cloud,
            experiment_name=self.config.experiment.name,
            experiment_version=self.config.experiment.version,
            experiment_dir=self._current_experiment_dir,
            output_path=self.config.experiment.output_path,
        )

    def _register_targets(self, model_filter: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a :class:`TargetFactory` and register targets.

        :param model_filter: Optional list of model names to limit registration to.
        :type model_filter: list[str] or None
        :returns: A dictionary mapping target names to their data.
        :rtype: dict[str, Any]
        """
        self._target_factory = TargetFactory(
            config=self.config,
            execution_context=self.execution_context,
            connections_registry=self.connections_registry,
            cloud_config=self.config.experiment.cloud,
            logger=self._logger,
        )
        return self._target_factory.register_targets(model_filter)

    # ------------------------------------------------------------------
    # Existing helpers
    # ------------------------------------------------------------------

    def _create_experiment_dir(self) -> Path:
        """Create the experiment output directory.

        :returns: The path to the created experiment directory.
        :rtype: Path
        """
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

            logger.debug("Registering evaluator: %s (class: %s)", effective_name, evaluator_name)
            evaluator_instance = evaluator_class(evaluator_dict, self.execution_context)
            self.evaluators_registry[effective_name] = evaluator_instance

    def load_dataset(
        self, dataset_config: Optional[DatasetConfig] = None, dataset_path: Optional[str] = None
    ) -> BaseDataset:
        """Load dataset from configuration.

        Uses :class:`DatasetFactory` for type routing and path overrides.

        :param dataset_config: Explicit dataset configuration. Falls back to the
            experiment config when ``None``.
        :type dataset_config: DatasetConfig or None
        :param dataset_path: Optional override path for the dataset file.
        :type dataset_path: str or None
        :returns: The loaded dataset.
        :rtype: BaseDataset
        """
        if dataset_config is None:
            dataset_config = self.config.experiment.dataset
            if dataset_config is None:
                raise ValueError("Dataset configuration required")

        factory = DatasetFactory()
        ds = factory.create_from_config(
            dataset_config,
            dataset_path_override=dataset_path,
            context=self.execution_context,
        )
        logger.info("Loaded dataset '%s' with %d record(s)", dataset_config.name, len(ds))
        return ds

    # ------------------------------------------------------------------
    # evaluate() and its helpers
    # ------------------------------------------------------------------

    def evaluate(self, dataset: BaseDataset) -> Dict[str, Any]:
        """Evaluate all models on the given dataset.

        :param dataset: The dataset to evaluate against.
        :type dataset: BaseDataset
        :returns: A summary dictionary with status, paths, and aggregated metrics.
        :rtype: dict[str, Any]
        """
        logger.info("Starting evaluation — %d record(s), %d target(s), %d evaluator(s)",
                     len(dataset), len(self.targets_registry), len(self.evaluators_registry))
        self._suppress_noisy_loggers()

        executor = self._create_executor()
        failed_records, first_error_msg = self._run_evaluation(executor, dataset)

        summary = self._build_summary(dataset, failed_records, first_error_msg)
        self._persist_outputs(summary)
        self._cleanup()

        if failed_records > 0:
            logger.warning("Evaluation completed with %d failed record(s)", failed_records)
        else:
            logger.info("Evaluation completed successfully")

        return summary

    def _suppress_noisy_loggers(self) -> None:
        """Suppress non-fatal warnings from SDK evaluators and LangChain callbacks."""
        for _logger_name in (
            "langchain_core.callbacks.manager",
            "langchain_core.callbacks",
            "langchain_azure_ai",
        ):
            logging.getLogger(_logger_name).setLevel(logging.ERROR)

    def _create_executor(self) -> EvaluationExecutor:
        """Instantiate and cache an :class:`EvaluationExecutor`.

        :returns: The evaluation executor for this run.
        :rtype: EvaluationExecutor
        """
        executor = EvaluationExecutor(
            evaluators_registry=self.evaluators_registry,
            trace_capture=self._trace_capture,
            experiment_dir=self._current_experiment_dir,
        )
        self._executor = executor
        return executor

    def _run_evaluation(
        self, executor: EvaluationExecutor, dataset: BaseDataset
    ) -> tuple:
        """Execute evaluation across all registered targets.

        :param executor: The evaluation executor.
        :type executor: EvaluationExecutor
        :param dataset: The dataset to evaluate.
        :type dataset: BaseDataset
        :returns: A tuple of ``(failed_records, first_error_msg)``.
        :rtype: tuple[int, str | None]
        """
        max_workers = self.config.experiment.max_workers or 4
        total_models = len(self.targets_registry)
        failed_records = 0
        first_error_msg: Optional[str] = None

        if total_models > 1:
            failed_records, first_error_msg = executor.evaluate_all_parallel(
                self.targets_registry, dataset, max_workers,
            )
        else:
            for model_name, model_data in self.targets_registry.items():
                output_path = self._current_experiment_dir / f"{model_name}_results.jsonl"
                failed = executor.evaluate_model(
                    dataset, model_name, model_data, output_path, max_workers,
                )
                failed_records += failed

        return failed_records, first_error_msg

    def _build_summary(
        self,
        dataset: BaseDataset,
        failed_records: int,
        first_error_msg: Optional[str],
    ) -> Dict[str, Any]:
        """Collect aggregated metrics and build the final summary dictionary.

        :param dataset: The evaluated dataset (used for record count).
        :type dataset: BaseDataset
        :param failed_records: Number of records that failed evaluation.
        :type failed_records: int
        :param first_error_msg: The first error message encountered, if any.
        :type first_error_msg: str or None
        :returns: The evaluation summary dictionary.
        :rtype: dict[str, Any]
        """
        total_models = len(self.targets_registry)
        total_records = len(dataset) * total_models

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

        summary: Dict[str, Any] = {
            "status": "completed_with_errors" if failed_records > 0 else "completed",
            "output_path": str(self._current_experiment_dir),
            "total_records": total_records,
            "failed_records": failed_records,
            "models_evaluated": total_models,
            "aggregated_evaluators": all_aggregated,
        }
        if first_error_msg:
            summary["first_error"] = first_error_msg

        return summary

    def _persist_outputs(self, summary: Dict[str, Any]) -> None:
        """Write AITK job artifacts and sidebar results to disk.

        :param summary: The summary dictionary to augment with artifact paths.
        :type summary: dict[str, Any]
        """
        aitk_job_path = self._output.persist_aitk_job_artifacts()
        if aitk_job_path is not None:
            summary["aitk_job_path"] = str(aitk_job_path)

        sidebar_path = self._output.persist_aitk_sidebar_results()
        if sidebar_path is not None:
            summary["aitk_sidebar_path"] = str(sidebar_path)

    def _cleanup(self) -> None:
        """Shut down resources acquired during the evaluation run."""
        if self._trace_capture is not None:
            self._trace_capture.shutdown()
