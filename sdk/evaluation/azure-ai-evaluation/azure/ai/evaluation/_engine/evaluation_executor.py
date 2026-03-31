"""Evaluation execution logic — runs inference + evaluators on dataset records."""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .evaluators_aggregator import MetricsAggregator
from .models import EvaluationOutput, InferenceOutput
from .progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)


class EvaluationExecutor:
    """Encapsulates the parallel evaluation execution pipeline.

    Responsible for running inference against targets, computing evaluator
    scores, collecting results, and aggregating metrics.  Extracted from
    :class:`ModelEvaluator` to separate orchestration from execution.
    """

    def __init__(
        self,
        evaluators_registry: Dict[str, Any],
        trace_capture: Optional[Any],
        experiment_dir: Path,
    ) -> None:
        self.evaluators_registry = evaluators_registry
        self._trace_capture = trace_capture
        self._experiment_dir = experiment_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_all_parallel(
        self,
        targets_registry: Dict[str, Any],
        dataset: Any,
        max_workers: int,
    ) -> tuple:
        """Evaluate all target variants in parallel with a shared multi-bar progress display.

        Returns:
            ``(total_failed, first_error_msg)`` tuple.
        """
        import threading

        records = list(dataset)  # materialize once for all variants
        total_failed = 0
        first_error = None
        lock = threading.Lock()

        # Prepare per-variant work items
        variant_items = []
        for model_name, model_data in targets_registry.items():
            output_path = self._experiment_dir / f"{model_name}_results.jsonl"
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
                                    self.evaluate_record,
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
                failed = self.evaluate_model(dataset, model_name, model_data, output_path, max_workers)
                total_failed += failed

        return total_failed, first_error

    def evaluate_model(
        self,
        dataset: Any,
        model_name: str,
        model_data: Dict[str, Any],
        output_path: Path,
        max_workers: int,
    ) -> int:
        """Evaluate a single model on dataset using ThreadPoolExecutor."""
        model_instance = model_data["model"]
        model_args = model_data["args"]
        model_config_name = model_data["config"].name
        target_mapping = getattr(model_data["config"], "mapping", {}) or {}

        run_name = f"run_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_id = run_name

        failed_count = 0

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for record in dataset:
                    future = executor.submit(
                        self.evaluate_record,
                        record,
                        run_id,
                        model_config_name,
                        model_name,
                        model_instance,
                        target_mapping=target_mapping,
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

    def evaluate_record(
        self,
        record: Dict[str, Any],
        run_id: str,
        model_name: str,
        model_display_name: str,
        model: Any,
        target_mapping: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> EvaluationOutput:
        """Evaluate a single record."""
        from .evaluator import _apply_target_input_mapping, _apply_target_output_mapping
        from .evaluator import _extract_tool_definitions_from_trace, _infer_tool_definitions_from_trace

        record_id = str(hash(json.dumps(record, sort_keys=True, default=str)))[:12]

        start_time = time.perf_counter()
        agent_trace = None

        # Apply target input mapping (dataset.X → target param)
        mapped_input = _apply_target_input_mapping(record, target_mapping or {})

        try:
            # Run inference — with OTel trace capture if enabled
            if self._trace_capture is not None:
                model_output, agent_trace = self._trace_capture.wrap_target_call(
                    target_fn=model.infer,
                    record=mapped_input,
                    model_name=model_name,
                    record_id=record_id,
                )
            else:
                model_output = model.infer(mapped_input)

            # Apply target output mapping (target.X → canonical name)
            if isinstance(model_output, dict):
                model_output = _apply_target_output_mapping(model_output, target_mapping or {})

            response_time_ms = (time.perf_counter() - start_time) * 1000

            # Auto-enrich output from OTel traces.
            # Targets just return {"response": text} — everything else comes from traces.
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
