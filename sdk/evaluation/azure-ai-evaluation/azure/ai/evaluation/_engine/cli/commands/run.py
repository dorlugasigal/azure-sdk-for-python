# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""run command — execute evaluation via ExperimentRunner."""
from __future__ import annotations

import contextlib
import os
import sys
from typing import Any, Dict, List, Optional

import click

from ..utils.constants import EV_ASCII
from ..utils.discovery import import_local_components, load_config_safe
from ..utils.output import echo, echo_error, has_rich, get_console, show_panel, show_results_table


@contextlib.contextmanager
def _working_directory(path: str):
    """Temporarily change cwd and extend sys.path, restoring both on exit."""
    original = os.getcwd()
    original_sys_path = sys.path.copy()
    try:
        abs_path = os.path.abspath(path)
        os.chdir(abs_path)
        if abs_path not in sys.path:
            sys.path.insert(0, abs_path)
        yield
    finally:
        os.chdir(original)
        sys.path[:] = original_sys_path


def _set_plain_output(_ctx, _param, value):
    """Eager callback to disable Rich formatting before the run command executes."""
    if value:
        os.environ["EV_DISABLE_RICH_LOGGING"] = "true"


@click.command()
@click.option("--path", "-p", default=".", type=click.Path(exists=True), help="Working directory for the experiment")
@click.option("--config", "-c", default=None, help="Path to config file (default: auto-detect)")
@click.option("--dataset", "-d", "dataset_path", required=False, default=None, help="Path to dataset file (overrides config)")
@click.option("--env", "-e", default=".env", help="Path to .env file")
@click.option("--remote", "-r", is_flag=True, help="Run on configured compute backend")
@click.option("--models", "-m", required=False, default=None, help="Comma-separated target names to evaluate")
@click.option("--auto-approve", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option("--output", "-o", default=None, help="Output path override")
@click.option("--stream-remote-logs", is_flag=True, default=False, help="Stream logs from remote compute to terminal (only applies with --remote)")
@click.option("--plain", is_flag=True, expose_value=False, is_eager=True, callback=_set_plain_output, help="Disable ASCII art and Rich formatting. Uses plain log output.")
@click.help_option("--help", "-h")
def run(path, config, dataset_path, env, remote, models, auto_approve, output, stream_remote_logs):
    """Run evaluation.

    By default, runs locally.
    Use --remote for Foundry cloud compute.

    \b
    Examples:
        ev run                           # Run locally
        ev run --remote                  # Run on Foundry cloud
        ev run --remote --stream-remote-logs  # Stream remote logs to terminal
        ev run -c custom.yaml            # Custom config
        ev run -m target_a,target_b      # Filter targets
        ev run --plain                   # Disable Rich formatting
    """
    _console = get_console()
    _HAS_RICH = has_rich()

    with _working_directory(path):
        # Banner
        if _HAS_RICH:
            _console.print(EV_ASCII, highlight=False)

        # Auto-detect config file
        _CONFIG_CANDIDATES = ["config.yaml", "evals.yaml", "experiment/config.yaml"]
        if config is None:
            for candidate in _CONFIG_CANDIDATES:
                if os.path.exists(candidate):
                    config = candidate
                    break
            if config is None:
                echo_error("No config file found.")
                echo(f"Searched: {', '.join(_CONFIG_CANDIDATES)}", err=True)
                echo("Run 'ev new <name>' to create a project, or specify --config path.", err=True)
                sys.exit(1)

        config_path = os.path.abspath(config) if os.path.isabs(config) else config
        if not os.path.exists(config_path):
            echo_error(f"Config file '{config}' not found.")
            echo("Run 'ev new <name>' to create a project, or specify --config path.", err=True)
            sys.exit(1)

        # Discover local components
        import_local_components(os.getcwd())

        # Parse --models filter
        model_filter: Optional[List[str]] = None
        if models:
            model_filter = [m.strip() for m in models.split(",") if m.strip()]

        # Load config for pre-run summary
        cfg = load_config_safe(config_path)

        compute_mode = "remote (Foundry)" if remote else "local"
        metric_names = ", ".join(m.name for m in cfg.experiment.evaluators) if cfg else "—"
        dataset_name = cfg.experiment.dataset.name if cfg else "—"
        experiment_name = cfg.experiment.name if cfg else "—"

        panel_info: Dict[str, str] = {
            "Config": config,
            "Experiment": experiment_name,
            "Compute": compute_mode,
            "Metrics": metric_names,
            "Dataset": dataset_name,
        }

        show_panel(panel_info, title="ev run")

        if not auto_approve and _HAS_RICH:
            _console.print()

        # Run via ExperimentRunner
        from azure.ai.evaluation._engine.runner import ExperimentRunner
        from azure.ai.evaluation._engine.compute import JobStatus

        env_path = env if os.path.exists(env) else None

        runner = ExperimentRunner()
        try:
            if remote and _HAS_RICH:
                # Remote path: use Rich status with live updates
                with _console.status("[bold cyan]Submitting to Foundry...") as status:
                    def _update_status(msg: str) -> None:
                        status.update(f"[bold cyan]{msg}")

                    job_info = runner.run(
                        config_path=config_path,
                        env_path=env_path,
                        dataset_path=dataset_path,
                        remote_compute=True,
                        model_filter=model_filter,
                        on_progress=_update_status,
                        stream_remote_logs=stream_remote_logs,
                    )
            elif remote:
                # Remote path without Rich
                def _print_progress(msg: str) -> None:
                    click.echo(msg)

                job_info = runner.run(
                    config_path=config_path,
                    env_path=env_path,
                    dataset_path=dataset_path,
                    remote_compute=True,
                    model_filter=model_filter,
                    on_progress=_print_progress,
                    stream_remote_logs=stream_remote_logs,
                )
            else:
                # Local path: evaluator shows its own Rich progress bar
                if not _HAS_RICH:
                    click.echo("Running evaluation...")
                job_info = runner.run(
                    config_path=config_path,
                    env_path=env_path,
                    dataset_path=dataset_path,
                    remote_compute=False,
                    model_filter=model_filter,
                )
        except Exception as e:
            echo_error(str(e))
            sys.exit(1)

        # Handle results based on job status
        if job_info.status == JobStatus.FAILED:
            error_msg = job_info.metadata.get("error", "Unknown error")
            echo_error(f"Evaluation failed: {error_msg}")
            sys.exit(1)
        elif job_info.status == JobStatus.COMPLETED:
            metadata = job_info.metadata
            execution_type = metadata.get("execution_type", "local")

            if execution_type == "local":
                # Local evaluation results
                show_results_table(metadata)

            else:
                # Remote / Foundry compute results
                remote_panel: Dict[str, str] = {
                    "Status": str(job_info.status.value),
                    "Job ID": job_info.job_id,
                }
                eval_id = metadata.get("eval_id")
                run_id = metadata.get("run_id")
                report_url = metadata.get("report_url")
                if eval_id:
                    remote_panel["Evaluation ID"] = eval_id
                if run_id:
                    remote_panel["Run ID"] = run_id
                show_panel(remote_panel, title="Foundry Cloud Compute — Evaluation Complete")

                # Print report URL separately so it's copyable
                if report_url:
                    echo(f"\n📊 Report: {report_url}\n")

            if output and _HAS_RICH:
                echo(f"\n[dim]Output saved to: {output}[/dim]")
        else:
            # Submitted / pending / running
            show_panel(
                {
                    "Status": str(job_info.status.value),
                    "Job ID": job_info.job_id,
                },
                title="Job Submitted",
            )
