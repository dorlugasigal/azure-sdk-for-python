"""CLI for azure-ai-evaluation v2.0 — local-evals command.

Ports the full evee CLI experience with compute/tracking backend separation.
"""
from __future__ import annotations

import ast
import contextlib
import importlib
import importlib.util
import json
import logging
import os
import shutil
import sys
from typing import Any, Dict, List, Optional

import click

# Lazy Rich imports — graceful degradation if rich is not installed
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax

    _console = Console()
    _err_console = Console(stderr=True)
    _HAS_RICH = True
except ImportError:  # pragma: no cover
    _HAS_RICH = False
    _console = None  # type: ignore[assignment]
    _err_console = None  # type: ignore[assignment]


LOCAL_EVALS_ASCII = r"""
  ██╗      ██████╗  ██████╗ █████╗ ██╗       ███████╗██╗   ██╗ █████╗ ██╗     ███████╗
  ██║     ██╔═══██╗██╔════╝██╔══██╗██║       ██╔════╝██║   ██║██╔══██╗██║     ██╔════╝
  ██║     ██║   ██║██║     ███████║██║ █████╗█████╗  ██║   ██║███████║██║     ███████╗
  ██║     ██║   ██║██║     ██╔══██║██║ ╚════╝██╔══╝  ╚██╗ ██╔╝██╔══██║██║     ╚════██║
  ███████╗╚██████╔╝╚██████╗██║  ██║███████╗  ███████╗ ╚████╔╝ ██║  ██║███████╗███████║
  ╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝  ╚══════╝  ╚═══╝  ╚═╝  ╚═╝╚══════╝╚══════╝
"""


# ---------------------------------------------------------------------------
# Output helpers — rich when available, plain click.echo fallback
# ---------------------------------------------------------------------------

def _echo(msg: str = "", *, err: bool = False) -> None:
    if _HAS_RICH:
        (_err_console if err else _console).print(msg)
    else:
        click.echo(msg, err=err)


def _echo_error(msg: str) -> None:
    if _HAS_RICH:
        _err_console.print(f"[bold red]Error:[/bold red] {msg}")
    else:
        click.echo(f"Error: {msg}", err=True)


def _show_panel(lines: Dict[str, str], *, title: str = "local-evals") -> None:
    """Display a key/value summary as a Rich Panel or plain text."""
    if _HAS_RICH:
        max_key = max(len(k) for k in lines)
        body = "\n".join(f"[bold]{k + ':':<{max_key + 1}}[/bold] {v}" for k, v in lines.items())
        _console.print(Panel(body, title=title, border_style="cyan", expand=False))
    else:
        click.echo(f"--- {title} ---")
        for k, v in lines.items():
            click.echo(f"  {k}: {v}")


def _show_results_table(results: Dict[str, Any]) -> None:
    """Display evaluation results as a rich table or plain text."""
    models_evaluated = results.get("models_evaluated", 1)
    total = results.get("total_records", 0)
    failed = results.get("failed_records", 0)
    status = results.get("status", "completed")
    output_path_str = results.get("output_path", "")
    aggregated = results.get("aggregated_evaluators", results.get("aggregated_metrics", {}))

    if _HAS_RICH:
        table = Table(title="Evaluation Results", border_style="green")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Status", f"[green]{status}[/green]" if status == "completed" else status)
        table.add_row("Records", str(total))
        table.add_row("Variants", str(models_evaluated))
        if failed:
            table.add_row("Failed", f"[red]{failed}[/red]")
        if output_path_str:
            table.add_row("Output", output_path_str)

        for metric_name, value in aggregated.items():
            if isinstance(value, dict):
                # Aggregated evaluator with sub-metrics — show the primary score
                for sub_key, sub_val in value.items():
                    if isinstance(sub_val, float):
                        table.add_row(sub_key, f"{sub_val:.4f}")
                    elif isinstance(sub_val, (int, str)):
                        table.add_row(sub_key, str(sub_val))
            elif isinstance(value, float):
                table.add_row(metric_name, f"{value:.4f}")
            else:
                table.add_row(metric_name, str(value))

        _console.print(table)
    else:
        click.echo(f"\n  Status:    {status}")
        click.echo(f"  Records:   {total}")
        click.echo(f"  Variants:  {models_evaluated}")
        if failed:
            click.echo(f"  Failed:    {failed}")
        if output_path_str:
            click.echo(f"  Output:    {output_path_str}")
        for metric_name, value in aggregated.items():
            if isinstance(value, dict):
                for sub_key, sub_val in value.items():
                    if isinstance(sub_val, float):
                        click.echo(f"  {sub_key}: {sub_val:.4f}")
                    elif isinstance(sub_val, (int, str)):
                        click.echo(f"  {sub_key}: {sub_val}")
            elif isinstance(value, float):
                click.echo(f"  {metric_name}: {value:.4f}")
            else:
                click.echo(f"  {metric_name}: {value}")


# ---------------------------------------------------------------------------
# Working-directory context manager
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def working_directory(path: str):
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


# ---------------------------------------------------------------------------
# Built-in evaluator catalogue (used by ``list`` command)
# ---------------------------------------------------------------------------

_BUILTIN_EVALUATORS = [
    ("f1_score", "local", "F1 score (precision/recall)"),
    ("bleu", "local", "BLEU score for translation quality"),
    ("rouge", "local", "ROUGE score for summarization quality"),
    ("meteor", "local", "METEOR score for translation quality"),
    ("gleu", "local", "GLEU score for translation quality"),
    ("relevance", "cloud", "Relevance (LLM-as-Judge, 1-5)"),
    ("coherence", "cloud", "Coherence scoring"),
    ("fluency", "cloud", "Fluency scoring"),
    ("groundedness", "cloud", "Groundedness scoring"),
    ("similarity", "cloud", "Semantic similarity"),
    ("qa", "cloud", "Question-answering quality"),
    ("content_safety", "cloud", "Content safety evaluation"),
    ("protected_material", "cloud", "Protected material detection"),
    ("retrieval", "cloud", "Retrieval quality scoring"),
    ("document_retrieval", "cloud", "Document retrieval evaluation"),
    ("response_completeness", "cloud", "Response completeness scoring"),
    ("intent_resolution", "cloud", "Intent resolution accuracy"),
    ("task_adherence", "cloud", "Task adherence scoring"),
    ("task_completion", "cloud", "Task completion evaluation"),
    ("tool_call_accuracy", "cloud", "Tool call accuracy evaluation"),
    ("tool_call_success", "cloud", "Tool call success rate"),
    ("tool_selection", "cloud", "Tool selection accuracy"),
    ("tool_input_accuracy", "cloud", "Tool input parameter accuracy"),
    ("tool_output_utilization", "cloud", "Tool output utilization"),
    ("code_vulnerability", "cloud", "Code vulnerability detection"),
    ("service_groundedness", "cloud", "Service groundedness scoring"),
    ("eci", "cloud", "ECI scoring"),
    ("xpia", "cloud", "Cross-prompt injection detection"),
    ("ungrounded_attributes", "cloud", "Ungrounded attribute detection"),
]


# ---------------------------------------------------------------------------
# Component discovery
# ---------------------------------------------------------------------------

def _import_local_components(directory: str) -> None:
    """Import Python files in directory (and subdirs) that contain @target, @evaluator, or @dataset decorators."""
    decorator_names = ("target", "model", "metric", "evaluator", "dataset")
    decorator_pattern = "|".join(f"@{d}" for d in decorator_names)

    for root, dirs, files in os.walk(directory):
        # Skip hidden dirs, __pycache__, node_modules, .venv
        dirs[:] = [d for d in dirs if not d.startswith((".","_")) and d not in ("node_modules", "venv")]
        for fname in files:
            if not fname.endswith(".py") or fname.startswith("_") or fname.startswith("demo_"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath) as f:
                    content = f.read()
                if any(f"@{d}" in content for d in decorator_names):
                    tree = ast.parse(content)
                    has_decorator = any(
                        isinstance(node, ast.ClassDef)
                        and any(
                            (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id in decorator_names)
                            or (isinstance(d, ast.Name) and d.id in decorator_names)
                            for d in node.decorator_list
                        )
                        for node in ast.walk(tree)
                    )
                    if has_decorator:
                        # Build module name relative to directory
                        rel_path = os.path.relpath(fpath, directory)
                        module_name = rel_path[:-3].replace(os.sep, ".")
                        if module_name not in sys.modules:
                            spec = importlib.util.spec_from_file_location(module_name, fpath)
                            if spec and spec.loader:
                                mod = importlib.util.module_from_spec(spec)
                                sys.modules[module_name] = mod
                                spec.loader.exec_module(mod)
            except Exception:
                pass


def _discover_project_components() -> Dict[str, List[str]]:
    """Discover @target, @metric, @dataset components from registries.

    Returns dict with keys 'targets', 'metrics', 'datasets' mapping to lists of names.
    """
    found: Dict[str, List[str]] = {"targets": [], "metrics": [], "datasets": []}
    try:
        from azure.ai.evaluation._engine.decorators import (
            TARGET_REGISTRY,
            METRIC_REGISTRY,
            DATASET_REGISTRY,
        )
        found["targets"] = sorted(TARGET_REGISTRY.keys())
        found["metrics"] = sorted(METRIC_REGISTRY.keys())
        found["datasets"] = sorted(DATASET_REGISTRY.keys())
    except ImportError:
        pass
    return found


def _load_config_safe(config_path: str):
    """Load Config from YAML, returning None on failure."""
    try:
        from azure.ai.evaluation._engine.config import Config
        return Config.from_yaml(config_path)
    except Exception:
        return None


def _dir_size_str(path: str) -> str:
    """Return human-readable size of a directory tree."""
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024:
            return f"{total:.1f} {unit}"
        total /= 1024
    return f"{total:.1f} TB"


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------

class OrderedGroup(click.Group):
    """Maintains command insertion order."""

    def list_commands(self, _ctx):
        return list(self.commands.keys())


@click.group(invoke_without_command=True, cls=OrderedGroup)
@click.version_option(version="2.0.0a1", prog_name="local-evals")
@click.pass_context
def main(ctx):
    """Azure AI Evaluation — local-first evaluation toolkit."""
    if ctx.invoked_subcommand is None:
        if _HAS_RICH:
            _console.print(LOCAL_EVALS_ASCII, style="cyan", highlight=False)
        click.echo(ctx.get_help())


# ---------------------------------------------------------------------------
# run — execute evaluation via ExperimentRunner
# ---------------------------------------------------------------------------

@main.command()
@click.option("--path", "-p", default=".", type=click.Path(exists=True), help="Working directory for the experiment")
@click.option("--config", "-c", default="evals.yaml", help="Path to config file")
@click.option("--dataset", "-d", "dataset_path", required=False, default=None, help="Path to dataset file (overrides config)")
@click.option("--env", "-e", default=".env", help="Path to .env file")
@click.option("--remote", "-r", is_flag=True, help="Run on configured compute backend")
@click.option("--models", "-m", required=False, default=None, help="Comma-separated target names to evaluate")
@click.option("--no-tracking", is_flag=True, help="Disable tracking backend")
@click.option("--auto-approve", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option("--output", "-o", default=None, help="Output path override")
@click.help_option("--help", "-h")
def run(path, config, dataset_path, env, remote, models, no_tracking, auto_approve, output):
    """Run evaluation.

    By default, runs locally with tracking if configured.
    Use --remote for Foundry cloud compute. Use --no-tracking to skip publishing.

    \b
    Examples:
        local-evals run                           # Run locally (publishes if tracking configured)
        local-evals run --no-tracking             # Run locally, skip publishing
        local-evals run --remote                  # Run on Foundry cloud
        local-evals run -c custom.yaml            # Custom config
        local-evals run -m target_a,target_b      # Filter targets
    """
    with working_directory(path):
        # Banner
        if _HAS_RICH:
            _console.print(LOCAL_EVALS_ASCII, style="cyan", highlight=False)

        config_path = os.path.abspath(config) if os.path.isabs(config) else config
        if not os.path.exists(config_path):
            _echo_error(f"Config file '{config}' not found.")
            _echo("Run 'local-evals new <name>' to create a project, or specify --config path.", err=True)
            sys.exit(1)

        # Discover local components
        _import_local_components(os.getcwd())

        # Parse --models filter
        model_filter: Optional[List[str]] = None
        if models:
            model_filter = [m.strip() for m in models.split(",") if m.strip()]

        # Load config for pre-run summary
        cfg = _load_config_safe(config_path)

        compute_mode = "remote (Foundry)" if remote else "local"
        metric_names = ", ".join(m.name for m in cfg.experiment.evaluators) if cfg else "—"
        dataset_name = cfg.experiment.dataset.name if cfg else "—"
        experiment_name = cfg.experiment.name if cfg else "—"

        # Determine tracking mode
        tracking_mode = "disabled" if no_tracking else "none"
        if not no_tracking and cfg:
            tb = getattr(cfg.experiment, "tracking_backend", None)
            if tb and getattr(tb, "type", "none") != "none":
                tracking_mode = getattr(tb, "type", "none")

        panel_info = {
            "Config": config,
            "Experiment": experiment_name,
            "Compute": compute_mode,
            "Metrics": metric_names,
            "Dataset": dataset_name,
        }
        if tracking_mode not in ("none", "disabled"):
            panel_info["Tracking"] = f"{tracking_mode} (results published to Foundry)"
        elif tracking_mode == "disabled":
            panel_info["Tracking"] = "disabled"

        _show_panel(panel_info, title="local-evals run")

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
                        tracking_enabled=not no_tracking,
                        model_filter=model_filter,
                        on_progress=_update_status,
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
                    tracking_enabled=not no_tracking,
                    model_filter=model_filter,
                    on_progress=_print_progress,
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
                    tracking_enabled=not no_tracking,
                    model_filter=model_filter,
                )
        except Exception as e:
            _echo_error(str(e))
            sys.exit(1)

        # Handle results based on job status
        if job_info.status == JobStatus.FAILED:
            error_msg = job_info.metadata.get("error", "Unknown error")
            _echo_error(f"Evaluation failed: {error_msg}")
            sys.exit(1)
        elif job_info.status == JobStatus.COMPLETED:
            metadata = job_info.metadata
            execution_type = metadata.get("execution_type", "local")

            if execution_type == "local":
                # Local evaluation results
                _show_results_table(metadata)

                # Show tracking URLs if results were published
                tracking_urls = metadata.get("tracking_urls", [])
                if tracking_urls:
                    _echo()
                    if _HAS_RICH:
                        _console.print("[bold green]📊 Results published to Foundry[/bold green]")
                    else:
                        click.echo("\n📊 Results published to Foundry:")
                    for url in tracking_urls:
                        _echo(url)
                elif metadata.get("tracking_backend"):
                    _echo(f"\n[dim]Tracking backend: {metadata['tracking_backend']}[/dim]" if _HAS_RICH else f"\nTracking backend: {metadata['tracking_backend']}")
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
                _show_panel(remote_panel, title="Foundry Cloud Compute — Evaluation Complete")

                # Print report URL separately so it's copyable
                if report_url:
                    _echo(f"\n📊 Report: {report_url}\n")

            if output and _HAS_RICH:
                _echo(f"\n[dim]Output saved to: {output}[/dim]")
        else:
            # Submitted / pending / running
            _show_panel(
                {
                    "Status": str(job_info.status.value),
                    "Job ID": job_info.job_id,
                },
                title="Job Submitted",
            )


# ---------------------------------------------------------------------------
# new — create evaluation project
# ---------------------------------------------------------------------------

@main.command()
@click.argument("name")
@click.help_option("--help", "-h")
def new(name: str):
    """Create a new evaluation project."""
    if os.path.exists(name):
        _echo_error(f"Directory '{name}' already exists.")
        sys.exit(1)

    os.makedirs(name)
    os.makedirs(os.path.join(name, "data"))

    config_template = '''experiment:
  name: "{name}"

  targets:
    - name: "my_target"
      type: "custom"
      args:
        temperature: [0.7]

  dataset:
    name: "eval_data"
    type: "jsonl"
    args:
      data_path: "data/samples.jsonl"

  metrics:
    - name: "relevance"
      mapping:
        query: "dataset.question"
        response: "model.answer"
        context: "dataset.context"

  connections:
    default:
      endpoint: "${{OPENAI_ENDPOINT:-http://localhost:11434/v1}}"
      api_key: "${{OPENAI_API_KEY:-not-needed}}"
'''
    config_path = os.path.join(name, "evals.yaml")
    with open(config_path, "w") as f:
        f.write(config_template.format(name=name))

    samples = [
        {"question": "What is machine learning?", "answer": "ML is a subset of AI that learns from data.", "context": "Machine learning is a branch of artificial intelligence."},
        {"question": "What is deep learning?", "answer": "Deep learning uses neural networks with many layers.", "context": "Deep learning is a subset of machine learning using neural networks."},
        {"question": "What is NLP?", "answer": "NLP processes human language with computers.", "context": "Natural language processing enables computers to understand human language."},
    ]
    data_path = os.path.join(name, "data", "samples.jsonl")
    with open(data_path, "w") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")

    custom_metric_code = '''"""Custom evaluator example — auto-discovered by evee engine."""
from azure.ai.evaluation._engine.decorators import metric, BaseMetric


@metric(name="word_count")
class WordCountMetric(BaseMetric):
    """Counts words in the response."""

    def compute(self, response: str = "", **kwargs):
        count = len(response.split())
        return {"word_count": count}

    def aggregate(self, scores):
        values = [s["word_count"] for s in scores]
        return {
            "word_count_mean": round(sum(values) / len(values), 1),
            "word_count_max": max(values),
            "word_count_min": min(values),
        }
'''
    with open(os.path.join(name, "custom_metrics.py"), "w") as f:
        f.write(custom_metric_code)

    if _HAS_RICH:
        _console.print(f"\n[bold green]✓[/bold green] Created evaluation project: [bold]{name}/[/bold]\n")
        tree_lines = [
            f"  [cyan]evals.yaml[/cyan]         — evaluation config",
            f"  [cyan]data/samples.jsonl[/cyan]  — sample dataset (3 records)",
            f"  [cyan]custom_metrics.py[/cyan]   — sample @metric evaluator",
        ]
        for line in tree_lines:
            _console.print(line)

        with open(config_path) as f:
            yaml_content = f.read()
        _console.print()
        _console.print(Syntax(yaml_content, "yaml", theme="monokai", line_numbers=False))

        _console.print(f"\n[bold]Next steps:[/bold]")
        _console.print(f"  cd {name}")
        _console.print(f"  local-evals run\n")
    else:
        click.echo(f"Created evaluation project: {name}/")
        click.echo(f"  evals.yaml         — evaluation config")
        click.echo(f"  data/samples.jsonl  — sample dataset (3 records)")
        click.echo(f"  custom_metrics.py   — sample @metric evaluator")
        click.echo(f"\nNext steps:")
        click.echo(f"  cd {name}")
        click.echo(f"  local-evals run")


# ---------------------------------------------------------------------------
# validate — check configuration
# ---------------------------------------------------------------------------

@main.command()
@click.option("--config", "-c", default="evals.yaml")
@click.option("--env", "-e", default=".env")
@click.help_option("--help", "-h")
def validate(config, env):
    """Validate configuration file."""
    if not os.path.exists(config):
        _echo_error(f"'{config}' not found.")
        sys.exit(1)

    # Load .env first so config can reference env vars
    if os.path.exists(env):
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env, override=True)
        except ImportError:
            pass

    try:
        from azure.ai.evaluation._engine.config import Config
        cfg = Config.from_yaml(config)

        info: Dict[str, str] = {
            "Targets": str(len(cfg.experiment.targets)),
            "Metrics": str(len(cfg.experiment.evaluators)),
            "Dataset": cfg.experiment.dataset.name if cfg.experiment.dataset else "—",
            "Output": getattr(cfg.experiment, "output_path", "experiment/output"),
        }

        compute_cfg = getattr(cfg.experiment, "compute", None)
        if compute_cfg:
            info["Compute"] = getattr(compute_cfg, "type", "local")

        tracking_cfg = getattr(cfg.experiment, "tracking_backend", None)
        if tracking_cfg:
            info["Tracking"] = getattr(tracking_cfg, "type", "none")

        if _HAS_RICH:
            _console.print(f"\n[bold green]✓[/bold green] Config valid: [bold]{cfg.experiment.name}[/bold]\n")
            _show_panel(info, title=cfg.experiment.name)
        else:
            click.echo(f"Config valid: {cfg.experiment.name}")
            for k, v in info.items():
                click.echo(f"  {k}: {v}")
    except Exception as e:
        _echo_error(f"Config invalid: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# list — discover and list available components
# ---------------------------------------------------------------------------

@main.command(name="list")
@click.option(
    "--type", "-t", "component_type",
    type=click.Choice(["all", "evaluators", "targets", "metrics", "datasets"]),
    default="all",
)
@click.help_option("--help", "-h")
def list_components(component_type):
    """Discover and list available components."""
    show_evaluators = component_type in ("all", "evaluators")
    show_project = component_type in ("all", "targets", "metrics", "datasets")

    # Built-in evaluators table
    if show_evaluators:
        evaluators = _BUILTIN_EVALUATORS
        if _HAS_RICH:
            table = Table(title="Built-in Evaluators", border_style="cyan")
            table.add_column("Name", style="bold")
            table.add_column("Type", justify="center")
            table.add_column("Description")

            for name, etype, desc in evaluators:
                type_style = "[green]local[/green]" if etype == "local" else "[blue]cloud[/blue]"
                table.add_row(name, type_style, desc)

            _console.print(table)
        else:
            click.echo("Built-in Evaluators:")
            click.echo(f"{'Name':<28} {'Type':<8} Description")
            click.echo("-" * 70)
            for name, etype, desc in evaluators:
                click.echo(f"{name:<28} {etype:<8} {desc}")

        _echo(f"\n[dim]{len(evaluators)} evaluators[/dim]" if _HAS_RICH else f"\n{len(evaluators)} evaluators")

    # Project components (discovered from cwd)
    if show_project:
        cwd = os.getcwd()
        if cwd not in sys.path:
            sys.path.insert(0, cwd)
        _import_local_components(cwd)
        found = _discover_project_components()

        sections = []
        if component_type in ("all", "targets"):
            sections.append(("Targets", found["targets"]))
        if component_type in ("all", "metrics"):
            sections.append(("Metrics", found["metrics"]))
        if component_type in ("all", "datasets"):
            sections.append(("Datasets", found["datasets"]))

        for label, names in sections:
            if _HAS_RICH:
                _console.print()
                if names:
                    table = Table(title=f"Project {label}", border_style="magenta")
                    table.add_column("Name", style="bold")
                    for n in names:
                        table.add_row(n)
                    _console.print(table)
                else:
                    _console.print(f"[dim]No project {label.lower()} discovered.[/dim]")
            else:
                click.echo(f"\nProject {label}:")
                if names:
                    for n in names:
                        click.echo(f"  {n}")
                else:
                    click.echo(f"  (none)")


# ---------------------------------------------------------------------------
# view — show evaluation results
# ---------------------------------------------------------------------------

@main.command()
@click.option("--port", "-p", "port", default=8765, help="Port to serve on (default: 8765)")
@click.option("--no-browser", is_flag=True, help="Don't automatically open browser")
@click.help_option("--help", "-h")
def view(port, no_browser):
    """View experiment results in your browser.

    Opens an interactive results viewer showing metrics across all targets.

    Examples:
        local-evals view
        local-evals view --port 9090
    """
    import http.server
    import signal
    import socketserver
    import threading
    import webbrowser
    from pathlib import Path

    output_dir = "experiment/output"

    def _find_experiments(base_dir):
        base = Path(base_dir)
        if not base.is_dir():
            return []
        experiments = []
        for child in sorted(base.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            if list(child.glob("*_results.jsonl")) or list(child.glob("*_summary.json")):
                experiments.append(child)
        return experiments

    def _load_results(exp_path):
        """Load results from an experiment directory into ViewResultsData format."""
        exp_path = Path(exp_path)
        models = []
        all_records = []
        all_metrics = {}

        def _find_primary_score(evaluator_name, values_dict):
            """Find the primary score from an evaluator's aggregated dict.

            Heuristic (matches Foundry portal behavior — one score per evaluator):
            1. {evaluator_name}_mean  (e.g. coherence → coherence_mean)
            2. {evaluator_name}       (exact key)
            3. Key containing 'score' AND ending in '_mean'
            4. First key ending in '_mean'
            5. Key named 'score'
            6. First numeric value
            """
            name = evaluator_name.lower()
            # 1. evaluator_name + _mean
            if f"{name}_mean" in values_dict:
                return values_dict[f"{name}_mean"]
            # 2. exact evaluator name as key
            if name in values_dict and isinstance(values_dict[name], (int, float)):
                return values_dict[name]
            # 3. key with 'score' and '_mean'
            for k, v in values_dict.items():
                if isinstance(v, (int, float)) and "score" in k and k.endswith("_mean"):
                    return v
            # 4. first key ending in _mean
            for k, v in values_dict.items():
                if isinstance(v, (int, float)) and k.endswith("_mean"):
                    return v
            # 5. key named 'score'
            if "score" in values_dict and isinstance(values_dict["score"], (int, float)):
                return values_dict["score"]
            # 6. first numeric value
            for v in values_dict.values():
                if isinstance(v, (int, float)):
                    return v
            return None

        def _flatten_agg(agg):
            """Extract one primary score per evaluator for the comparison view.

            Matches Foundry portal behavior: one score per evaluator (e.g.
            coherence: 4.0, response_completeness: 0.976) instead of hoisting
            all sub-keys to top level.
            """
            flat = {}
            for evaluator_name, evaluator_val in agg.items():
                if isinstance(evaluator_val, dict):
                    primary = _find_primary_score(evaluator_name, evaluator_val)
                    if primary is not None:
                        flat[evaluator_name] = primary
                elif isinstance(evaluator_val, (int, float)):
                    flat[evaluator_name] = evaluator_val
            return flat

        for summary_file in sorted(exp_path.glob("*_summary.json")):
            model_name = summary_file.stem.replace("_summary", "")
            results_file = exp_path / f"{model_name}_results.jsonl"

            with open(summary_file) as f:
                summary_data = json.load(f)

            records = []
            if results_file.exists():
                with open(results_file) as f:
                    for line in f:
                        if line.strip():
                            records.append(json.loads(line))

            agg = _flatten_agg(summary_data.get("aggregated_evaluators", summary_data.get("aggregated_metrics", {})))
            # Add standard overview
            agg["number_of_records"] = summary_data.get("total_records", len(records))
            # Compute average response time from records
            times = [r.get("system_evaluators", r.get("system_metrics", {})).get("response_time", {}).get("response_time_ms", 0) for r in records]
            if times:
                agg["average_response_time_ms"] = sum(times) / len(times)

            all_metrics.update(agg)

            # Build tags from first record's args
            base_name = model_name.split("__")[0] if "__" in model_name else model_name
            display_name = model_name.split("__", 1)[1] if "__" in model_name else model_name
            tags = {"model_name": base_name}
            if records:
                tags.update({k: v for k, v in records[0].get("args", {}).items()})

            models.append({
                "model_name": model_name,
                "model_display_name": display_name,
                "summary": {
                    "run_id": model_name,
                    "aggregated_evaluators": agg,
                    "tags": tags,
                },
                "records": records,
                "files": {
                    "summary": str(summary_file),
                    "records": str(results_file) if results_file.exists() else None,
                },
            })
            all_records.extend(records)

        return {
            "summary": {
                "run_id": exp_path.name,
                "aggregated_evaluators": all_metrics,
                "tags": {},
            },
            "records": all_records,
            "output_path": str(exp_path),
            "models": models,
        }

    # Resolve output directory
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    experiments = _find_experiments(output_dir)
    if not experiments:
        # No experiments yet — launch UI with empty data to show empty state
        results_data = {
            "experiment_name": "",
            "output_path": "",
            "models": [],
            "summary": {},
            "records": [],
        }
        output_path = output_dir
    else:
        output_path = str(experiments[0])

    if experiments:
        try:
            results_data = _load_results(output_path)
        except Exception as e:
            _echo_error(f"Failed to load results: {e}")
            sys.exit(1)

    # Load the viewer HTML template
    viewer_html_path = Path(__file__).parent / "_engine" / "ui" / "results_viewer.html"
    if not viewer_html_path.exists():
        _echo_error("Results viewer UI not found. The UI component may not be installed.")
        sys.exit(1)

    html_template = viewer_html_path.read_text()

    def _build_html():
        """Re-read data from disk and inject into HTML on every request."""
        current_experiments = _find_experiments(output_dir)
        if current_experiments:
            try:
                current_data = _load_results(str(current_experiments[0]))
            except Exception:
                current_data = {"experiment_name": "", "output_path": "", "models": [], "summary": {}, "records": []}
        else:
            current_data = {"experiment_name": "", "output_path": "", "models": [], "summary": {}, "records": []}

        safe_json = json.dumps(current_data).replace("</", "<\\/")
        safe_dir = json.dumps(output_dir).replace("</", "<\\/")
        inject_script = (
            "<script>\n"
            f"        window.__EVEE_RESULTS_DATA__ = {safe_json};\n"
            f"        window.__EVEE_OUTPUT_DIR__ = {safe_dir};\n"
            "    </script>"
        )
        return html_template.replace("</head>", f"{inject_script}</head>")

    class _ViewerHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(_build_html().encode())
            elif self.path == "/api/experiments":
                experiments = _find_experiments(output_dir)
                data = []
                for e in experiments:
                    info = {"name": e.name, "path": str(e)}
                    # Gather summary metadata for the overview page
                    summaries = sorted(e.glob("*_summary.json"))
                    info["num_runs"] = len(summaries)
                    info["created"] = e.stat().st_mtime
                    # Collect metric names and status from first summary
                    metric_names = []
                    if summaries:
                        try:
                            with open(summaries[0]) as sf:
                                first_summary = json.load(sf)
                            agg = first_summary.get("aggregated_metrics", {})
                            for k, v in agg.items():
                                if isinstance(v, dict):
                                    metric_names.extend(v.keys())
                                else:
                                    metric_names.append(k)
                        except Exception:
                            pass
                    info["metrics"] = [m for m in metric_names if "fail" not in m.lower()
                                       and m not in ("number_of_records", "average_response_time_ms")]
                    info["status"] = "Completed"
                    data.append(info)
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            elif self.path.startswith("/api/results/"):
                exp_name = self.path[len("/api/results/"):].strip("/")
                if not exp_name or "/" in exp_name or ".." in exp_name:
                    self.send_response(400)
                    self.end_headers()
                    return
                experiments = _find_experiments(output_dir)
                matched = next((e for e in experiments if e.name == exp_name), None)
                if matched is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                try:
                    data = _load_results(str(matched))
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(data).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
            else:
                self.send_error(404)

        def log_message(self, format, *args):
            pass  # Suppress request logs

    try:
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("127.0.0.1", port), _ViewerHandler) as httpd:
            url = f"http://localhost:{port}"
            if _HAS_RICH:
                _console.print(f"\n[green]✓[/green] Results viewer running at: [cyan]{url}[/cyan]")
                _console.print("[dim]Press Ctrl+C to stop[/dim]\n")
            else:
                click.echo(f"\n✓ Results viewer running at: {url}")
                click.echo("Press Ctrl+C to stop\n")

            if not no_browser:
                threading.Timer(0.5, lambda: webbrowser.open(url)).start()

            def _shutdown(_sig, _frame):
                if _HAS_RICH:
                    _console.print("\n[yellow]Stopping server...[/yellow]")
                else:
                    click.echo("\nStopping server...")
                httpd.shutdown()
                httpd.server_close()

            signal.signal(signal.SIGINT, _shutdown)
            signal.signal(signal.SIGTERM, _shutdown)
            httpd.serve_forever()
    except OSError as e:
        if "Address already in use" in str(e):
            _echo_error(f"Port {port} is already in use. Try: local-evals view --port {port + 1}")
            sys.exit(1)
        raise


def _display_result_summary(summary_path: str) -> None:
    """Load and display a summary.json file."""
    try:
        with open(summary_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        _echo_error(f"Failed to read '{summary_path}': {e}")
        sys.exit(1)

    if _HAS_RICH:
        _console.print(Syntax(json.dumps(data, indent=2), "json", theme="monokai", line_numbers=False))
    else:
        click.echo(json.dumps(data, indent=2))

    # Also display as a results table if the data has the right shape
    if "aggregated_metrics" in data or "total_records" in data:
        _show_results_table(data)


# ---------------------------------------------------------------------------
# clear — clean experiment output
# ---------------------------------------------------------------------------

@main.command()
@click.option("--path", "-p", default="experiment/output", help="Output directory to clean")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.help_option("--help", "-h")
def clear(path, force):
    """Clear experiment output folders."""
    if not os.path.isdir(path):
        _echo_error(f"Directory '{path}' does not exist.")
        sys.exit(1)

    subdirs = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
    if not subdirs:
        _echo("No output folders to clear.")
        return

    if _HAS_RICH:
        table = Table(title="Output Folders", border_style="yellow")
        table.add_column("Folder", style="bold")
        table.add_column("Size", justify="right")
        for d in sorted(subdirs):
            table.add_row(d, _dir_size_str(os.path.join(path, d)))
        _console.print(table)
    else:
        click.echo("Output folders:")
        for d in sorted(subdirs):
            click.echo(f"  {d}  ({_dir_size_str(os.path.join(path, d))})")

    if not force:
        if not click.confirm(f"\nDelete {len(subdirs)} folder(s) from '{path}'?"):
            _echo("Cancelled.")
            return

    removed = 0
    for d in subdirs:
        full = os.path.join(path, d)
        try:
            shutil.rmtree(full)
            removed += 1
        except OSError as e:
            _echo_error(f"Failed to remove '{full}': {e}")

    _echo(f"[bold green]✓[/bold green] Removed {removed} folder(s)." if _HAS_RICH else f"Removed {removed} folder(s).")


# ---------------------------------------------------------------------------
# compute — show compute backend configuration
# ---------------------------------------------------------------------------

@main.command()
@click.option("--config", "-c", default="evals.yaml")
@click.help_option("--help", "-h")
def compute(config):
    """Show compute backend configuration."""
    if not os.path.exists(config):
        _echo_error(f"Config file '{config}' not found.")
        sys.exit(1)

    cfg = _load_config_safe(config)
    if cfg is None:
        _echo_error(f"Failed to parse '{config}'.")
        sys.exit(1)

    compute_cfg = getattr(cfg.experiment, "compute", None)
    if compute_cfg:
        info = {
            "Type": getattr(compute_cfg, "type", "local"),
        }
        project = getattr(compute_cfg, "azure_ai_project", None)
        if project:
            info["Project"] = project
        deployment = getattr(compute_cfg, "deployment_name", None)
        if deployment:
            info["Deployment"] = deployment
    else:
        info = {"Type": "local (default)"}

    _show_panel(info, title="Compute Backend")


# ---------------------------------------------------------------------------
# tracking — show tracking backend configuration
# ---------------------------------------------------------------------------

@main.command()
@click.option("--config", "-c", default="evals.yaml")
@click.help_option("--help", "-h")
def tracking(config):
    """Show tracking backend configuration."""
    if not os.path.exists(config):
        _echo_error(f"Config file '{config}' not found.")
        sys.exit(1)

    cfg = _load_config_safe(config)
    if cfg is None:
        _echo_error(f"Failed to parse '{config}'.")
        sys.exit(1)

    tracking_cfg = getattr(cfg.experiment, "tracking_backend", None)
    if tracking_cfg:
        info = {
            "Type": getattr(tracking_cfg, "type", "none"),
        }
        project = getattr(tracking_cfg, "azure_ai_project", None)
        if project:
            info["Project"] = project
        deployment = getattr(tracking_cfg, "deployment_name", None)
        if deployment:
            info["Deployment"] = deployment
    else:
        info = {"Type": "none (disabled)"}

    _show_panel(info, title="Tracking Backend")


# ---------------------------------------------------------------------------
# model / metric / dataset — info shortcuts (model kept as backward compat)
# ---------------------------------------------------------------------------

@main.command(name="target")
@click.argument("name", required=False)
@click.help_option("--help", "-h")
def target_cmd(name):
    """Show target information or list discovered targets."""
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    _import_local_components(cwd)
    found = _discover_project_components()

    if name:
        if name in found["targets"]:
            _echo(f"[bold green]✓[/bold green] Target '{name}' is registered." if _HAS_RICH else f"Target '{name}' is registered.")
        else:
            _echo_error(f"Target '{name}' not found. Available: {', '.join(found['targets']) or '(none)'}")
            sys.exit(1)
    else:
        if found["targets"]:
            for m in found["targets"]:
                _echo(f"  {m}")
        else:
            _echo("No targets discovered. Add a @target decorated class to your project.")


@main.command()
@click.argument("name", required=False)
@click.help_option("--help", "-h")
def metric(name):
    """Show metric information or list discovered metrics."""
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    _import_local_components(cwd)
    found = _discover_project_components()

    if name:
        if name in found["metrics"]:
            _echo(f"[bold green]✓[/bold green] Metric '{name}' is registered." if _HAS_RICH else f"Metric '{name}' is registered.")
        else:
            _echo_error(f"Metric '{name}' not found. Available: {', '.join(found['metrics']) or '(none)'}")
            sys.exit(1)
    else:
        if found["metrics"]:
            for m in found["metrics"]:
                _echo(f"  {m}")
        else:
            _echo("No metrics discovered. Add a @metric decorated class to your project.")


@main.command()
@click.argument("name", required=False)
@click.help_option("--help", "-h")
def dataset(name):
    """Show dataset information or list discovered datasets."""
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    _import_local_components(cwd)
    found = _discover_project_components()

    if name:
        if name in found["datasets"]:
            _echo(f"[bold green]✓[/bold green] Dataset '{name}' is registered." if _HAS_RICH else f"Dataset '{name}' is registered.")
        else:
            _echo_error(f"Dataset '{name}' not found. Available: {', '.join(found['datasets']) or '(none)'}")
            sys.exit(1)
    else:
        if found["datasets"]:
            for d in found["datasets"]:
                _echo(f"  {d}")
        else:
            _echo("No datasets discovered. Add a @dataset decorated class to your project.")


if __name__ == "__main__":
    main()
