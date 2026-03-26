"""Metrics aggregation for evaluation results."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from .decorators import BaseEvaluator

logger = logging.getLogger(__name__)


@dataclass
class AggregatedMetrics:
    """Aggregated metrics for an evaluation run."""

    run_id: str
    aggregated_metrics: Dict[str, Any]
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "aggregated_metrics": self.aggregated_metrics,
            "tags": self.tags,
        }


class MetricsAggregator:
    """Aggregates per-record evaluator scores across an entire dataset.

    Reads evaluation results (JSONL) produced by the engine, delegates
    aggregation to each registered evaluator's ``aggregate`` method, and
    returns a single :class:`AggregatedMetrics` summary.
    """

    def __init__(self, evaluator_registry: Dict[str, BaseEvaluator]) -> None:
        """
        Args:
            evaluator_registry: Mapping of evaluator names to evaluator instances.
        """
        self.evaluator_registry = evaluator_registry

    @staticmethod
    def _add_evaluator_prefix(evaluator_name: str, aggregated_values: Dict[str, Any]) -> Dict[str, Any]:
        """Prefix each numeric aggregated value with the evaluator name.

        Args:
            evaluator_name: Name of the evaluator.
            aggregated_values: Raw aggregated dict returned by the evaluator.

        Returns:
            New dict with keys in the form ``"<evaluator> - <key>"``.
        """
        return {
            f"{evaluator_name} - {key}": value
            for key, value in aggregated_values.items()
            if isinstance(value, (int, float))
        }

    def analyze_results(self, results_path: Path) -> AggregatedMetrics:
        """Aggregate evaluator scores from a JSONL results file.

        Each line in the file is expected to be a JSON object produced by
        :meth:`EvaluationOutput.to_dict` (see ``models.py``).

        Args:
            results_path: Path to the ``.jsonl`` results file.

        Returns:
            :class:`AggregatedMetrics` with per-evaluator aggregated scores,
            failure counts, and average response time.

        Raises:
            Exception: If the results file cannot be read or parsed.
        """
        try:
            evaluator_scores: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            evaluator_failures: Dict[str, int] = defaultdict(int)
            record_count = 0
            tags: Dict[str, str] = {}
            run_id = ""
            total_response_time = 0.0

            with open(results_path) as fh:
                for line in fh:
                    record = json.loads(line)
                    record_count += 1

                    # Capture tags from the first record
                    if record_count == 1:
                        run_id = record.get("run_id", "")
                        tags = {
                            **record.get("args", {}),
                            **record.get("metadata", {}),
                            "target_name": record.get("model_display_name", record.get("model_name", "")),
                        }

                    # Collect per-evaluator scores (engine emits both "evaluators" and "metrics")
                    evaluators_dict = record.get("evaluators", record.get("metrics", {}))
                    for evaluator_name, scores in evaluators_dict.items():
                        if scores is None:
                            evaluator_failures[evaluator_name] += 1
                            continue
                        evaluator_scores[evaluator_name].append(scores)

                    # Accumulate response time from system evaluators / system metrics
                    system = record.get("system_evaluators", record.get("system_metrics", {}))
                    rt = system.get("response_time", {})
                    total_response_time += rt.get("response_time_ms", 0)

            # Build failure report (only evaluators with > 0 failures)
            failures_report = {
                f"{name} - Fail count": count
                for name, count in evaluator_failures.items()
                if count > 0
            }

            all_metrics: Dict[str, Any] = {
                "number_of_records": record_count,
                "average_response_time_ms": int(total_response_time / record_count) if record_count > 0 else 0,
                **failures_report,
            }

            # Delegate to each evaluator's aggregate()
            for evaluator_name, scores_list in evaluator_scores.items():
                if evaluator_name not in self.evaluator_registry:
                    logger.warning("Evaluator '%s' not found in registry — skipping aggregation.", evaluator_name)
                    continue

                evaluator_instance = self.evaluator_registry[evaluator_name]
                try:
                    aggregated = evaluator_instance.aggregate(scores_list)
                except Exception:
                    logger.exception("Failed to aggregate evaluator '%s'", evaluator_name)
                    aggregated = {"Aggregation Failed": -1}

                prefixed = self._add_evaluator_prefix(evaluator_name, aggregated)
                all_metrics.update(prefixed)

            return AggregatedMetrics(
                run_id=run_id,
                aggregated_metrics=all_metrics,
                tags=tags,
            )

        except Exception:
            logger.exception("Failed to analyze results file: '%s'", results_path)
            raise
