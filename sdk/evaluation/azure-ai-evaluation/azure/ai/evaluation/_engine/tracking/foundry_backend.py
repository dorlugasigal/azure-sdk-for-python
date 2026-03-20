"""Foundry tracking backend — publishes local evaluation results to Azure AI Foundry."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .backend import TrackingBackend
from .constants import OperationStatus
from .events import (
    ArtifactGeneratedEvent,
    ExperimentCompletedEvent,
    ExperimentStartEvent,
    InferenceCompletedEvent,
    InferenceStartEvent,
    ModelRunCompletedEvent,
    ModelRunStartEvent,
    ResultsAnalyzedEvent,
)

logger = logging.getLogger(__name__)


def _format_variant_name(variant: str) -> str:
    """Format a variant name for display in Foundry UI.

    Handles both simplified names ('model__baseline') and full names
    ('model__max_tokens=200_prompt=baseline_temperature=0.7').
    """
    if "__" not in variant:
        return variant
    _, suffix = variant.split("__", 1)
    # If it contains key=value pairs, parse them properly
    if "=" in suffix:
        parts = suffix.split("=")
        pairs: List[str] = []
        current_key = parts[0]
        for i in range(1, len(parts)):
            if i == len(parts) - 1:
                pairs.append(f"{current_key}={parts[i]}")
            else:
                last_us = parts[i].rfind("_")
                if last_us >= 0:
                    pairs.append(f"{current_key}={parts[i][:last_us]}")
                    current_key = parts[i][last_us + 1:]
                else:
                    pairs.append(f"{current_key}={parts[i]}")
        return ", ".join(pairs)
    # Simple suffix (e.g., "baseline", "few_shot")
    return suffix


class FoundryTrackingBackend(TrackingBackend):
    """Publishes local evaluation results to Azure AI Foundry.

    Flow:
    1. on_experiment_started: Connect to Foundry, store experiment name + config
    2. start_run: Store model run info
    3. on_inference_completed: Collect per-record results
    4. on_results_analyzed: Store aggregated metrics
    5. on_run_completed: Submit eval + run to Foundry with collected data
    6. on_experiment_completed / on_shutdown: Cleanup
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._azure_ai_project = (config or {}).get("azure_ai_project", "")
        self._openai_client = None
        self._project_client = None
        self._eval_lock = threading.Lock()  # guards _eval_object_id creation

        # Per-experiment state
        self._experiment_name = ""
        self._experiment_config: Dict[str, Any] = {}
        self._eval_object_id: Optional[str] = None  # one eval for the whole experiment
        self._eval_created = False

        # Per-run state (reset in start_run)
        self._current_run_id = ""
        self._current_model_name = ""
        self._collected_records: List[Dict[str, Any]] = []
        self._input_records: Dict[str, Dict[str, Any]] = {}  # record_id -> original input + scores
        self._aggregated_metrics: Dict[str, Any] = {}
        self._run_count = 0

        # Published results (accessible after evaluation)
        self.published_urls: List[str] = []

    def on_startup(self) -> None:
        """Connect to Azure AI Foundry."""
        if not self._azure_ai_project:
            logger.warning("FoundryTrackingBackend: no azure_ai_project configured, will skip publishing")
            return

        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
            self._project_client = AIProjectClient(
                endpoint=self._azure_ai_project,
                credential=credential,
            )
            self._openai_client = self._project_client.get_openai_client()
            logger.info(f"FoundryTrackingBackend: connected to {self._azure_ai_project}")
        except ImportError:
            logger.warning("FoundryTrackingBackend: azure-ai-projects not installed, skipping")
        except Exception as e:
            logger.warning(f"FoundryTrackingBackend: failed to connect: {e}")

    def on_experiment_started(self, event: ExperimentStartEvent) -> None:
        self._experiment_name = event.experiment_name
        self._experiment_config = event.config

    def start_run(self, event: ModelRunStartEvent) -> Optional[str]:
        """Start a new model run — reset per-run collection state."""
        self._current_run_id = event.run_id
        self._current_model_name = event.model_name
        self._collected_records = []
        self._input_records = {}
        self._aggregated_metrics = {}
        return event.run_id

    def on_inference_started(self, event: InferenceStartEvent) -> None:
        """Collect original input data for later submission."""
        self._input_records[event.record_id] = event.input_data

    def on_inference_completed(self, event: InferenceCompletedEvent) -> None:
        """Collect per-record output data and merge metric scores into input records."""
        self._collected_records.append({
            "record_id": event.record_id,
            "status": str(event.status),
            "duration_ms": event.duration_ms,
            "output": event.output_data,
        })

        # Merge per-record metric scores into the input record so they can be
        # uploaded as part of the JSONL items and read back by pass-through graders.
        metrics = event.output_data.get("metrics", {})
        if metrics and event.record_id in self._input_records:
            for metric_name, metric_value in metrics.items():
                score = self._extract_score(metric_name, metric_value)
                if score is not None:
                    self._input_records[event.record_id][f"__score_{metric_name}"] = str(score)

    def on_results_analyzed(self, event: ResultsAnalyzedEvent) -> None:
        """Store aggregated metrics."""
        self._aggregated_metrics = event.metrics or {}

    def on_artifact_generated(self, event: ArtifactGeneratedEvent) -> None:
        """Could upload artifacts, but for now just log."""
        logger.debug(f"FoundryTrackingBackend: artifact generated: {event.artifact_path} ({event.artifact_type})")

    def on_run_completed(self, event: ModelRunCompletedEvent) -> None:
        """Submit the collected results to Foundry as a run under the experiment's eval."""
        if not self._openai_client:
            return
        if event.status == OperationStatus.FAILED:
            logger.warning(f"FoundryTrackingBackend: run {event.run_id} failed, skipping publish")
            return

        try:
            try:
                from rich.console import Console
                _con = Console()
                def _print(msg: str) -> None:
                    _con.print(f"  [cyan]⠿[/cyan] {msg}", highlight=False)
                def _success(msg: str) -> None:
                    _con.print(f"  [bold green]✓[/bold green] {msg}")
            except ImportError:
                def _print(msg: str) -> None:
                    print(f"  {msg}")
                def _success(msg: str) -> None:
                    print(f"  ✓ {msg}")

            self._publish_run_to_foundry(on_status=_print)
            self._run_count += 1
            _success(f"Published '{_format_variant_name(self._current_model_name)}' to Foundry")
        except Exception as e:
            logger.warning(f"FoundryTrackingBackend: failed to publish run: {e}")

    def on_experiment_completed(self, event: ExperimentCompletedEvent) -> None:
        """Log the eval URL once after all runs are published."""
        if self._eval_object_id and self.published_urls:
            try:
                from rich.console import Console
                Console().print()  # blank line before results table
            except ImportError:
                pass
        logger.info(f"FoundryTrackingBackend: experiment '{event.experiment_name}' completed ({self._run_count} runs)")

    def on_shutdown(self) -> None:
        self._openai_client = None
        self._project_client = None

    # -------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------

    @staticmethod
    def _extract_score(metric_name: str, metric_value: Any) -> Optional[float]:
        """Extract a numeric score from a metric result.

        Metric results may be a plain float, or a dict like {"f1_score": 0.85}.
        Returns None if the value cannot be interpreted as a score.
        """
        if isinstance(metric_value, (int, float)):
            return float(metric_value)
        if isinstance(metric_value, dict):
            # Try the metric name itself as key, then common keys
            for key in (metric_name, "score", "value"):
                if key in metric_value:
                    val = metric_value[key]
                    if isinstance(val, (int, float)):
                        return float(val)
            # Fall back to the first numeric value in the dict
            for val in metric_value.values():
                if isinstance(val, (int, float)):
                    return float(val)
        return None

    def _ensure_eval_created(self, sample_record: Dict[str, Any], on_status=None) -> str:
        """Create the Foundry eval once (lazy), return eval_id. Reused across runs.

        Uses PythonGrader pass-through graders to import pre-computed metric scores
        instead of re-running evaluators on the cloud.
        """
        if self._eval_object_id:
            return self._eval_object_id

        def _status(msg: str) -> None:
            if on_status:
                on_status(msg)

        _status("Creating evaluation on Foundry...")

        # Build schema from dataset fields (includes __score_* fields)
        properties: Dict[str, Any] = {k: {"type": "string"} for k in sample_record}

        from openai.types.eval_create_params import DataSourceConfigCustom
        data_source_config = DataSourceConfigCustom(
            type="custom",
            item_schema={
                "type": "object",
                "properties": properties,
                "required": list(sample_record.keys()),
            },
        )

        # Build pass-through PythonGrader testing criteria from config metrics.
        # Each grader reads its pre-computed score from the item data.
        metrics_config = (
            self._experiment_config
            .get("experiment", {})
            .get("metrics", [])
        )

        testing_criteria: List[Dict[str, Any]] = []
        for mc in metrics_config:
            metric_name = mc.get("name", "")
            if not metric_name:
                continue

            score_field = f"__score_{metric_name}"
            # Only add a grader if we have pre-computed scores in the data
            if score_field not in sample_record:
                logger.debug(f"FoundryTrackingBackend: no pre-computed score for '{metric_name}', skipping")
                continue

            grader_source = (
                f"def grade(sample, item):\n"
                f"    \"\"\"Pass-through grader for pre-computed {metric_name} scores.\"\"\"\n"
                f"    value = item.get(\"{score_field}\")\n"
                f"    if value is None:\n"
                f"        return 0.0\n"
                f"    try:\n"
                f"        return float(value)\n"
                f"    except (TypeError, ValueError):\n"
                f"        return 0.0\n"
            )

            testing_criteria.append({
                "type": "python",
                "name": metric_name,
                "source": grader_source,
            })

        if not testing_criteria:
            raise ValueError(
                "No pre-computed metric scores found in evaluation results. "
                "Ensure metrics are configured and computed locally before publishing."
            )

        eval_object = self._openai_client.evals.create(
            name=self._experiment_name,
            data_source_config=data_source_config,
            testing_criteria=testing_criteria,
        )
        self._eval_object_id = eval_object.id

        # Build portal URL (same for all runs under this eval)
        from ..foundry_compute import _build_portal_url
        portal_url = _build_portal_url(self._azure_ai_project, eval_object.id)
        if portal_url:
            self.published_urls.append(portal_url)

        return eval_object.id

    def _publish_run_to_foundry(self, on_status=None) -> None:
        """Add a run to the experiment's eval with the collected records."""
        if not self._openai_client or not self._input_records:
            return

        def _status(msg: str) -> None:
            if on_status:
                on_status(msg)

        original_records = list(self._input_records.values())
        _status(f"Publishing '{self._current_model_name}' ({len(original_records)} records)...")

        # Ensure eval exists (created once, reused for all runs)
        with self._eval_lock:
            eval_id = self._ensure_eval_created(original_records[0], on_status=on_status)

        from openai.types.evals.create_eval_jsonl_run_data_source_param import (
            CreateEvalJSONLRunDataSourceParam,
            SourceFileContent,
            SourceFileContentContent,
        )

        items = []
        for record in original_records:
            clean = {k: str(v) if not isinstance(v, str) else v for k, v in record.items()}
            items.append(SourceFileContentContent(item=clean))

        run_display = _format_variant_name(self._current_model_name)

        _status(f"Submitting run '{run_display}'...")
        eval_run = self._openai_client.evals.runs.create(
            eval_id=eval_id,
            name=run_display,
            data_source=CreateEvalJSONLRunDataSourceParam(
                type="jsonl",
                source=SourceFileContent(
                    type="file_content",
                    content=items,
                ),
            ),
        )

        _status("Waiting for Foundry to process...")
        run = eval_run
        for _ in range(60):
            run = self._openai_client.evals.runs.retrieve(
                run_id=eval_run.id,
                eval_id=eval_id,
            )
            if run.status in ("completed", "failed", "cancelled"):
                break
            _status(f"Foundry processing '{self._current_model_name}'... ({run.status})")
            time.sleep(3)
