"""Output formatting and persistence for evaluation results."""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AITK_JOBS_DIR_ENV = "AITK_EVALS_JOBS_DIR"


class OutputFormatter:
    """Handles output persistence and formatting for evaluation results.

    Extracts file-I/O and result-building logic that was previously embedded
    in :class:`ModelEvaluator`.
    """

    def __init__(
        self,
        current_dir: Path,
        experiment_dir: Path,
        config_path: str,
        experiment_name: str,
        dataset_config: Any,
        evaluator_configs: Optional[List[Any]],
    ) -> None:
        self._current_dir = current_dir
        self._current_experiment_dir = experiment_dir
        self._config_path = config_path
        self._experiment_name = experiment_name
        self._dataset_config = dataset_config
        self._evaluator_configs = evaluator_configs

    def persist_aitk_sidebar_results(self) -> Optional[Path]:
        """Write a flat rows JSON to <workspace>/test-results/ for the AITK sidebar tree.

        The AI Toolkit extension's "View Local Evaluation Results" tree node scans
        <vscode_workspace>/test-results/**/*.json and shows each file.  Clicking a
        file opens it in the Data Viewer.  The Data Viewer auto-selects a root-level
        array, so we write just the rows array as the JSON root to give the user an
        immediate tabular view of inputs/outputs.
        """
        try:
            consolidated_results = self.build_consolidated_results_payload()
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

    def persist_aitk_job_artifacts(self) -> Optional[Path]:
        """Copy evaluate-style artifacts into AI Toolkit jobs folder.

        The Evaluation pane consumes per-job artifacts from ~/.aitk/evals/jobs.
        This writes a consolidated results.json plus lightweight metadata there
        for discovery.
        """
        consolidated_results = self.build_consolidated_results_payload()
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
            dataset_cfg = self._dataset_config
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
                for ev in (self._evaluator_configs or [])
            ]

            # The extension's parseJobMetadata requires: id, input, status
            metadata = {
                "id": self._current_experiment_dir.name,
                "input": {
                    "evalName": self._experiment_name,
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

    def build_consolidated_results_payload(self) -> Optional[Dict[str, Any]]:
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
                                for sub_name, sub_value in evaluator_data.items():
                                    row[f"outputs.{evaluator_name}.{sub_name}"] = sub_value

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
