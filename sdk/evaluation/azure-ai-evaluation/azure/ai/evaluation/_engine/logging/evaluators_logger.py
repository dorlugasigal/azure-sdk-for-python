"""Thread-safe local evaluators logger for evaluation artifacts.

Persists individual inference results (JSONL) and aggregated evaluator
summaries (JSON) to the local filesystem.
"""
from __future__ import annotations

import json
import os
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

from .logger import setup_logger


class LocalEvaluatorsLogger:
    """Persist evaluation artifacts to the local filesystem.

    Appends individual inference results to log files in a thread-safe
    manner and saves aggregated evaluator summaries as JSON files.
    """

    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.logger = setup_logger(self.__class__.__module__)
        self._locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._locks_guard = threading.Lock()
        os.makedirs(output_dir, exist_ok=True)

    def _get_lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks[key]

    # ------------------------------------------------------------------
    # Inference results
    # ------------------------------------------------------------------

    def log_inference_result(self, evaluation_output: Any, output_path: Path) -> None:
        """Append a single evaluation result as a JSONL line.

        Parameters
        ----------
        evaluation_output:
            An object exposing a ``to_dict()`` method (e.g.
            :class:`~azure.ai.evaluation._engine.models.EvaluationOutput`).
        output_path:
            Path to the JSONL results file.
        """
        try:
            with self._get_lock(str(output_path)), open(output_path, "a") as fh:
                fh.write(json.dumps(evaluation_output.to_dict()) + "\n")
            self.logger.debug("Successfully saved evaluation result to %s", output_path)
        except Exception:
            self.logger.exception("Failed to save model inference result")
            raise

    # ------------------------------------------------------------------
    # Aggregated results
    # ------------------------------------------------------------------

    def log_results(self, results: Any, results_path: Path) -> Path:
        """Save aggregated evaluators to a JSON file.

        Parameters
        ----------
        results:
            An object exposing ``to_dict()``, ``run_id``, ``tags``, and
            ``aggregated_evaluators`` attributes (e.g. ``AggregatedEvaluators``).
        results_path:
            Path to the raw results artefact.  The output file is derived
            from this path's stem.

        Returns
        -------
        Path
            Path to the saved results JSON file.
        """
        try:
            output_file = f"{results_path.stem}_results.json"
            output_path = Path(self.output_dir) / output_file

            with open(output_path, "w") as fh:
                json.dump(results.to_dict(), fh, indent=2)

            self.logger.debug(
                "Analyzed Results Summary for run ID %s\nTags: %s\nAggregated Evaluators: %s\nSaved to: %s",
                results.run_id,
                results.tags,
                results.aggregated_evaluators,
                output_path,
            )
            return output_path
        except Exception:
            self.logger.exception("Failed to analyze and log results for '%s'", results_path)
            raise
