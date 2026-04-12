"""Evaluation execution logic — runs inference + evaluators on dataset records."""
from __future__ import annotations

import contextvars
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .evaluators_aggregator import EvaluatorsAggregator
from ..models.evaluation_output import EvaluationOutput
from ..models.inference_output import InferenceOutput
from ..progress_tracker import ProgressTracker

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
        variant_results: List[Tuple[int, Optional[str]]] = []

        variant_items = [
            (name, data, self._experiment_dir / f"{name}_results.jsonl")
            for name, data in targets_registry.items()
        ]

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
                tasks = {
                    name: progress.add_task(f"  {name}", total=len(records))
                    for name, _, _ in variant_items
                }

                def _on_advance(model_name: str) -> None:
                    progress.advance(tasks[model_name])

                def _run_and_collect(model_name, model_data, output_path):
                    result = self._execute_single_variant(
                        model_name, model_data, output_path, records,
                        max_workers, lock, _on_advance,
                    )
                    with lock:
                        variant_results.append(result)

                threads = []
                for model_name, model_data, output_path in variant_items:
                    t = threading.Thread(
                        target=_run_and_collect,
                        args=(model_name, model_data, output_path),
                        daemon=True,
                    )
                    t.start()
                    threads.append(t)

                for t in threads:
                    t.join()

                for failed, error in variant_results:
                    total_failed += failed
                    if error and first_error is None:
                        first_error = error

        except ImportError:
            # No Rich — fall back to sequential
            for model_name, model_data, output_path in variant_items:
                failed = self.evaluate_model(dataset, model_name, model_data, output_path, max_workers)
                total_failed += failed

        return total_failed, first_error

    def _execute_single_variant(
        self,
        model_name: str,
        model_data: Dict[str, Any],
        output_path: Path,
        records: List[Dict[str, Any]],
        max_workers: int,
        lock: Any,
        on_advance: Any = None,
    ) -> Tuple[int, Optional[str]]:
        """Run a single model variant against all records.

        Args:
            model_name: Display name for the variant.
            model_data: Dict with ``model``, ``args``, and ``config`` keys.
            output_path: Path for JSONL result output.
            records: Materialised dataset records.
            max_workers: Thread pool size for record-level parallelism.
            lock: Shared threading lock for error aggregation.
            on_advance: Optional callback invoked after each record completes.

        Returns:
            ``(failed_count, first_error_message)`` for this variant.
        """
        model_instance = model_data["model"]
        model_args = model_data["args"]
        model_config_name = model_data["config"].name

        run_id = f"run_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        variant_failed = 0
        first_error = None

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        contextvars.copy_context().run, self.evaluate_record,
                        record, run_id, model_config_name,
                        model_name, model_instance, **model_args,
                    )
                    for record in records
                ]

                for future in as_completed(futures):
                    try:
                        eval_output = future.result()
                        self._save_result(eval_output, output_path)
                    except Exception as exc:
                        variant_failed += 1
                        logger.error("Record evaluation failed: %s", exc)
                        with lock:
                            if first_error is None:
                                first_error = str(exc)
                    if on_advance is not None:
                        on_advance(model_name)

            self._aggregate_and_save_evaluators(output_path, model_name)
        except Exception as exc:
            variant_failed = len(records)
            logger.error("Variant '%s' failed: %s", model_name, exc)
            with lock:
                if first_error is None:
                    first_error = str(exc)

        return variant_failed, first_error

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
        target_mapping = getattr(model_data["config"], "input_mapping", {}) or {}

        run_id = f"run_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    contextvars.copy_context().run, self.evaluate_record,
                    record, run_id, model_config_name, model_name,
                    model_instance, target_mapping=target_mapping, **model_args,
                )
                for record in dataset
            ]

            failed_count = self._collect_results_with_progress(
                futures, model_name, len(futures), output_path,
            )

        self._aggregate_and_save_evaluators(output_path, model_name)
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
        """Evaluate a single record: infer, trace, score.

        Orchestrates the full per-record pipeline: input mapping → inference
        → output enrichment → evaluator computation → event emission.
        """
        from .evaluator import _apply_target_input_mapping

        record_id = str(hash(json.dumps(record, sort_keys=True, default=str)))[:12]
        mapped_input = _apply_target_input_mapping(record, target_mapping or {})

        model_output, agent_trace, response_time_ms = self._run_inference(
            model, mapped_input, model_name, record_id,
        )

        if isinstance(model_output, dict):
            self._enrich_output_from_trace(model_output, agent_trace)
            self._extract_tools_from_output_items(model_output)
            self._resolve_tool_definitions(model_output, agent_trace)
            self._ensure_output_items(model_output, record)

        inference_output = self._build_inference_output(
            model_output, model_name, record, kwargs, agent_trace,
        )
        evaluator_results = self._compute_evaluators(inference_output)
        self._emit_trace_events(agent_trace, evaluator_results)
        system_metrics = self._build_system_metrics(response_time_ms, agent_trace)

        return EvaluationOutput(
            run_id=run_id,
            inference_output=inference_output,
            evaluators=evaluator_results,
            system_evaluators=system_metrics,
            model_display_name=model_display_name,
            metadata={},
        )

    # ------------------------------------------------------------------
    # evaluate_record helpers
    # ------------------------------------------------------------------

    def _run_inference(
        self,
        model: Any,
        mapped_input: Dict[str, Any],
        model_name: str,
        record_id: str,
    ) -> Tuple[Any, Any, float]:
        """Call model.infer with timing and optional OTel trace capture.

        Returns:
            ``(model_output, agent_trace_or_None, response_time_ms)``
        """
        start = time.perf_counter()
        agent_trace = None

        if self._trace_capture is not None:
            model_output, agent_trace = self._trace_capture.wrap_target_call(
                target_fn=model.infer,
                record=mapped_input,
                model_name=model_name,
                record_id=record_id,
            )
        else:
            model_output = model.infer(mapped_input)

        response_time_ms = (time.perf_counter() - start) * 1000
        return model_output, agent_trace, response_time_ms

    @staticmethod
    def _enrich_output_from_trace(
        model_output: Dict[str, Any],
        agent_trace: Any,
    ) -> None:
        """Populate output_items, tool_calls, and tool_definitions from OTel trace data.

        Targets typically return ``{"response": text}``; everything else is
        extracted from the captured agent trace when available.
        """
        has_trace_data = (
            agent_trace is not None
            and (agent_trace.spans or agent_trace.llm_calls or agent_trace.log_events)
        )
        if not has_trace_data:
            return

        from .evaluator import _extract_tool_definitions_from_trace

        if "output_items" not in model_output:
            model_output["output_items"] = agent_trace.to_conversation_format()
            # Only populate tool_calls from trace when output_items also came
            # from the trace.  When the target already returned output_items,
            # _extract_tools_from_output_items will derive more accurate
            # tool_calls (with proper arguments) from them.
            if "tool_calls" not in model_output:
                model_output["tool_calls"] = agent_trace.to_tool_calls_format()
        if "tool_definitions" not in model_output:
            tool_defs = _extract_tool_definitions_from_trace(agent_trace)
            if tool_defs:
                model_output["tool_definitions"] = tool_defs

    @staticmethod
    def _extract_tools_from_output_items(model_output: Dict[str, Any]) -> None:
        """Extract tool_definitions and tool_calls from output_items.

        Handles multiple formats:
        - Foundry MCP agents: ``mcp_list_tools`` and ``mcp_call`` items
        - OpenAI Responses API: ``tool_call`` entries in message content
        - Standard conversation format: tool_call content in assistant messages

        When tool_definitions are not explicitly provided, infers them from
        tool_call content in the conversation (matching Vienna's approach).
        """
        output_items = model_output.get("output_items")
        if not isinstance(output_items, list):
            return

        # --- Extract tool_calls ---
        if "tool_calls" not in model_output:
            tool_calls = []
            for item in output_items:
                if not isinstance(item, dict):
                    continue

                item_type = item.get("type", "")

                # Foundry MCP format
                if item_type == "mcp_call":
                    tool_calls.append({
                        "type": "tool_call",
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", {}),
                        "output": item.get("output", ""),
                    })
                    continue

                # OpenAI/standard conversation format — tool_calls in content
                content = item.get("content")
                if isinstance(content, list):
                    for entry in content:
                        if isinstance(entry, dict) and entry.get("type") == "tool_call":
                            args = entry.get("arguments", {})
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except (json.JSONDecodeError, ValueError):
                                    pass
                            tool_calls.append({
                                "type": "tool_call",
                                "name": entry.get("name", ""),
                                "arguments": args,
                            })

            if tool_calls:
                model_output["tool_calls"] = tool_calls

        # --- Extract tool_definitions ---
        if "tool_definitions" not in model_output:
            tool_defs: List[Dict[str, Any]] = []

            # 1. From MCP mcp_list_tools items
            for item in output_items:
                if isinstance(item, dict) and item.get("type") == "mcp_list_tools":
                    for tool in item.get("tools", []):
                        tool_defs.append({
                            "type": "function",
                            "name": tool.get("name", ""),
                            "description": tool.get("description", tool.get("name", "")),
                            "parameters": tool.get("inputSchema", tool.get("parameters", {})),
                        })

            # 2. Infer from tool_call content in messages (Vienna approach)
            if not tool_defs:
                inferred: Dict[str, Dict[str, Any]] = {}
                all_tool_calls = model_output.get("tool_calls", [])
                for tc in all_tool_calls:
                    name = tc.get("name", "")
                    if not name or name in inferred:
                        continue
                    args = tc.get("arguments", {})
                    props = {}
                    if isinstance(args, dict):
                        for k, v in args.items():
                            if isinstance(v, bool):
                                props[k] = {"type": "boolean"}
                            elif isinstance(v, int):
                                props[k] = {"type": "integer"}
                            elif isinstance(v, float):
                                props[k] = {"type": "number"}
                            else:
                                props[k] = {"type": "string"}
                    inferred[name] = {
                        "type": "function",
                        "name": name,
                        "description": name,
                        "parameters": {"type": "object", "properties": props},
                    }
                tool_defs = list(inferred.values())

            if tool_defs:
                model_output["tool_definitions"] = tool_defs

    @staticmethod
    def _resolve_tool_definitions(
        model_output: Dict[str, Any],
        agent_trace: Any,
    ) -> None:
        """Ensure tool_definitions is populated, inferring from tool_calls when needed.

        Covers cases where OTel doesn't capture ``gen_ai.request.tools``.
        """
        if "tool_definitions" in model_output or not model_output.get("tool_calls"):
            return

        from .evaluator import _infer_tool_definitions_from_trace

        inferred = _infer_tool_definitions_from_trace(agent_trace) if agent_trace else []
        if not inferred:
            tool_definitions_by_name: Dict[str, Dict[str, Any]] = {}
            for tool_call in model_output["tool_calls"]:
                name = tool_call.get("name", "")
                if name and name not in tool_definitions_by_name:
                    args = tool_call.get("arguments", {})
                    props = {k: {"type": "string"} for k in args} if isinstance(args, dict) else {}
                    tool_definitions_by_name[name] = {
                        "type": "function", "name": name, "description": name,
                        "parameters": {"type": "object", "properties": props},
                    }
            inferred = list(tool_definitions_by_name.values())

        if inferred:
            model_output["tool_definitions"] = inferred

    @staticmethod
    def _ensure_output_items(
        model_output: Dict[str, Any],
        record: Dict[str, Any],
    ) -> None:
        """Add fallback output_items and prepend user query for evaluator conversation parsing."""
        response_text = model_output.get("response") or model_output.get("answer")

        # Fallback: minimal output_items from response/answer text
        if "output_items" not in model_output and response_text:
            model_output["output_items"] = [
                {"role": "assistant", "content": [{"type": "text", "text": str(response_text)}]}
            ]

        if "output_items" not in model_output:
            return

        items = model_output["output_items"]

        # Filter out non-conversation items (mcp_list_tools, mcp_call, etc.)
        # that lack a 'role' field — evaluators expect OpenAI conversation format.
        conversation_types = {"message", None}
        items[:] = [
            item for item in items
            if isinstance(item, dict) and (
                "role" in item
                or item.get("type") in conversation_types
            )
        ]

        # Prepend user query for evaluator conversation parser
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

    @staticmethod
    def _build_inference_output(
        model_output: Any,
        model_name: str,
        record: Dict[str, Any],
        args: Dict[str, Any],
        agent_trace: Any,
    ) -> InferenceOutput:
        """Construct an ``InferenceOutput``, attaching trace data when available."""
        inference_output = InferenceOutput(
            output=model_output, model_name=model_name, record=record, args=args,
        )
        if agent_trace is not None:
            inference_output.agent_trace = agent_trace
        return inference_output

    def _compute_evaluators(
        self,
        inference_output: InferenceOutput,
    ) -> Dict[str, Any]:
        """Run every registered evaluator on the inference output.

        Returns:
            Dict mapping evaluator name → result dict (or error dict).
        """
        evaluator_results: Dict[str, Any] = {}
        for evaluator_name, evaluator_instance in self.evaluators_registry.items():
            try:
                evaluator_results[evaluator_name] = evaluator_instance.compute(inference_output)
            except Exception as eval_err:
                evaluator_results[evaluator_name] = {"error": f"computation_failed: {eval_err}"}
        return evaluator_results

    def _emit_trace_events(
        self,
        agent_trace: Any,
        evaluator_results: Dict[str, Any],
    ) -> None:
        """Emit OTel evaluation-result events for each scored evaluator."""
        if agent_trace is None or self._trace_capture is None:
            return

        for eval_name, eval_result in evaluator_results.items():
            if not isinstance(eval_result, dict) or "error" in eval_result:
                continue

            score_val: Optional[float] = None
            score_label: Optional[str] = None
            explanation: Optional[str] = None
            for key, value in eval_result.items():
                if isinstance(value, (int, float)):
                    score_val = float(value)
                elif isinstance(value, str) and key in ("label", "result"):
                    score_label = value
                elif isinstance(value, str) and key in ("reason", "explanation"):
                    explanation = value

            self._trace_capture.emit_evaluation_result(
                trace_id=agent_trace.trace_id,
                span_id=agent_trace.parent_span_id,
                evaluator_name=eval_name,
                score_value=score_val,
                score_label=score_label,
                explanation=explanation,
            )

    @staticmethod
    def _build_system_metrics(
        response_time_ms: float,
        agent_trace: Any,
    ) -> Dict[str, Any]:
        """Build the system_evaluators dict (response time + trace metrics)."""
        metrics: Dict[str, Any] = {
            "response_time": {"response_time_ms": response_time_ms},
        }
        if agent_trace is not None:
            metrics["trace"] = {
                "llm_call_count": len(agent_trace.llm_calls),
                "total_input_tokens": agent_trace.total_input_tokens,
                "total_output_tokens": agent_trace.total_output_tokens,
                "total_llm_duration_ms": agent_trace.total_duration_ms,
                "tool_call_count": len(agent_trace.tool_calls),
            }
        return metrics

    # ------------------------------------------------------------------
    # General internal helpers
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

        Uses :class:`EvaluatorsAggregator` for the core aggregation logic.

        Returns:
            Aggregated evaluators dictionary.
        """
        if not results_path.exists():
            return {}

        aggregator = EvaluatorsAggregator(self.evaluators_registry)
        analysis = aggregator.analyze_results(results_path)

        # Reconstruct per-evaluator breakdown from prefixed metrics
        aggregated: Dict[str, Any] = {}
        for evaluator_name in self.evaluators_registry:
            prefix = f"{evaluator_name} - "
            evaluator_values: Dict[str, Any] = {}
            for key, value in analysis.aggregated_evaluators.items():
                if key.startswith(prefix):
                    short_key = key[len(prefix):]
                    if short_key == "Aggregation Failed":
                        evaluator_values = {"error": "aggregation_failed"}
                        break
                    evaluator_values[short_key] = value
            if evaluator_values:
                aggregated[evaluator_name] = evaluator_values

        # Save summary
        total_records = analysis.aggregated_evaluators.get("number_of_records", 0)
        summary = {
            "model": model_name,
            "total_records": total_records,
            "aggregated_evaluators": aggregated,
        }

        summary_path = results_path.parent / f"{model_name}_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        return aggregated
