# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""evaluator command group — discover, add, and list evaluation evaluators."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import click

from ..utils.constants import BUILTIN_EVALUATORS, resolve_config_path
from ..utils.discovery import import_local_components, discover_project_components
from ..utils.output import echo, echo_error, has_rich


DEFAULT_CONFIG = "config.yaml"

TEMPLATE_TYPE_EMPTY = "empty"
TEMPLATE_TYPE_BUILTIN = "builtin"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def read_evaluators_from_config(config_path: Path) -> List[Dict[str, Any]]:
    """Read evaluator configurations from the YAML config."""
    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return []

    if not data or "experiment" not in data:
        return []

    experiment = data["experiment"]
    evaluators = experiment.get("evaluators", experiment.get("metrics", []))
    return evaluators if evaluators else []


def evaluator_exists_in_config(config_path: Path, name: str) -> bool:
    """Return ``True`` if an evaluator with *name* already exists in config."""
    return any(e.get("name") == name for e in read_evaluators_from_config(config_path))


def add_evaluator_to_config(
    config_path: Path,
    name: str,
    mapping: Dict[str, str] | None = None,
) -> bool:
    """Add or replace an evaluator entry in the config YAML."""
    try:
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.preserve_quotes = True  # type: ignore[assignment]

        with open(config_path, encoding="utf-8") as f:
            data = yaml.load(f)
        if data is None:
            data = {}

        experiment = data.setdefault("experiment", {})

        if "evaluators" not in experiment and "metrics" in experiment:
            key = "metrics"
        else:
            key = "evaluators"

        evaluators = experiment.setdefault(key, [])

        entry: Dict[str, Any] = {"name": name}
        if mapping:
            entry["mapping"] = mapping

        replaced = False
        for i, e in enumerate(evaluators):
            if isinstance(e, dict) and e.get("name") == name:
                evaluators[i] = entry
                replaced = True
                break
        if not replaced:
            evaluators.append(entry)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        return True
    except Exception:
        return False


def _snake_to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


# ---------------------------------------------------------------------------
# Evaluator file template
# ---------------------------------------------------------------------------

EMPTY_EVALUATOR_TEMPLATE = '''\
"""Custom evaluator: {class_name}."""

from azure.ai.evaluation._engine.decorators import evaluator, BaseEvaluator


@evaluator(name="{name}")
class {class_name}(BaseEvaluator):
    """TODO: Describe what this evaluator measures."""

    def compute(self, response: str = "", **kwargs):
        """Compute metric for a single record.

        Args:
            response: The model response to evaluate.
            **kwargs: Additional mapped fields from config.

        Returns:
            Dict with metric scores.
        """
        # TODO: implement your scoring logic
        return {{"{name}": 0.0}}

    def aggregate(self, scores):
        """Aggregate scores across all records.

        Args:
            scores: List of dicts returned by compute().

        Returns:
            Dict with aggregated scores.
        """
        values = [s["{name}"] for s in scores if "{name}" in s]
        if not values:
            return {{"{name}_mean": 0.0}}
        return {{
            "{name}_mean": round(sum(values) / len(values), 4),
            "{name}_max": max(values),
            "{name}_min": min(values),
        }}
'''


# ---------------------------------------------------------------------------
# Click commands
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.pass_context
def evaluator(ctx):
    """Manage evaluators — add, list, or show discovered evaluators."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@evaluator.command()
@click.option("--config", "-c", type=click.Path(), default=None, help="Path to config.")
@click.option("--verbose", "-v", is_flag=True, help="Show mapping and details.")
@click.help_option("--help", "-h")
def list(config, verbose):
    """List configured and discovered evaluators."""
    _HAS_RICH = has_rich()

    # Discover custom evaluators from project files
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    import_local_components(cwd)
    found = discover_project_components()

    # Read configured evaluators from config
    config = resolve_config_path(config)
    config_path = Path(config)
    configured = read_evaluators_from_config(config_path) if config_path.exists() else []

    # Configured evaluators
    if configured:
        echo(
            f"\n[bold cyan]Configured ({len(configured)}):[/bold cyan]"
            if _HAS_RICH else f"\nConfigured ({len(configured)}):"
        )
        # Check which are builtin vs custom
        builtin_names = {name for name, _, _ in BUILTIN_EVALUATORS}
        for eval_config in configured:
            name = eval_config.get("name", "unknown")
            tag = "[dim](built-in)[/dim]" if name in builtin_names else "[dim](custom)[/dim]"
            tag_plain = "(built-in)" if name in builtin_names else "(custom)"
            if verbose:
                mapping = eval_config.get("mapping", {})
                mapping_str = ", ".join(f"{k}={v}" for k, v in mapping.items()) if mapping else ""
                echo(f"  {name}  {tag}  {mapping_str}" if _HAS_RICH else f"  {name}  {tag_plain}  {mapping_str}")
            else:
                echo(f"  {name}  {tag}" if _HAS_RICH else f"  {name}  {tag_plain}")
    else:
        echo("\nNo evaluators configured.")

    # Discovered custom evaluators (from @evaluator decorated files)
    custom = found.get("evaluators", [])
    if custom:
        echo(
            f"\n[bold cyan]Discovered custom ({len(custom)}):[/bold cyan]"
            if _HAS_RICH else f"\nDiscovered custom ({len(custom)}):"
        )
        for name in custom:
            in_config = any(e.get("name") == name for e in configured)
            status = "[green]✓[/green]" if in_config else "[dim]not in config[/dim]"
            status_plain = "✓" if in_config else "not in config"
            echo(f"  {name}  {status}" if _HAS_RICH else f"  {name}  {status_plain}")

    if not configured and not custom:
        echo("\nAdd an evaluator with:")
        echo(f"  ev evaluator add --type {TEMPLATE_TYPE_EMPTY} --name my_evaluator")
        echo(f"  ev evaluator add --type {TEMPLATE_TYPE_BUILTIN} --name f1_score")


@evaluator.command()
@click.option(
    "--type",
    "-t",
    "evaluator_type",
    required=True,
    type=click.Choice([TEMPLATE_TYPE_EMPTY, TEMPLATE_TYPE_BUILTIN]),
    help="Evaluator type: 'empty' (custom template) or 'builtin' (built-in evaluator).",
)
@click.option("--name", "-n", required=True, help="Evaluator name (snake_case for empty, evaluator name for builtin).")
@click.option("--output", "-o", type=click.Path(), default=".", help="Output directory for evaluator file (default: current dir).")
@click.option(
    "--config",
    "-c",
    type=click.Path(),
    default=None,
    help="Path to config file (default: config.yaml).",
)
@click.option("--force", "-F", is_flag=True, help="Overwrite existing evaluator file and config.")
@click.help_option("--help", "-h")
def add(evaluator_type, name, output, config, force):
    """Add a new evaluator to your project.

    Examples:\n
      ev evaluator add --type empty --name accuracy\n
      ev evaluator add --type builtin --name f1_score\n
      ev evaluator builtins
    """
    config = resolve_config_path(config)
    config_path = Path(config)

    if config_path.exists() and not force and evaluator_exists_in_config(config_path, name):
        echo_error(f"Evaluator '{name}' already exists in config. Use --force to overwrite.")
        raise click.Abort()

    if evaluator_type == TEMPLATE_TYPE_EMPTY:
        _create_empty_evaluator(name, Path(output), config_path, force)
    elif evaluator_type == TEMPLATE_TYPE_BUILTIN:
        _add_builtin_evaluator(name, config_path, force)


def _create_empty_evaluator(name: str, output_dir: Path, config_path: Path, force: bool):
    """Create an empty evaluator from template."""
    _HAS_RICH = has_rich()
    class_name = _snake_to_pascal(name)
    evaluator_file = output_dir / f"{name}_evaluator.py"

    if evaluator_file.exists() and not force:
        echo_error(f"Evaluator file already exists: {evaluator_file}. Use --force to overwrite.")
        raise click.Abort()

    content = EMPTY_EVALUATOR_TEMPLATE.format(name=name, class_name=class_name)
    evaluator_file.parent.mkdir(parents=True, exist_ok=True)
    evaluator_file.write_text(content, encoding="utf-8")

    echo(
        f"[bold green]✅[/bold green] Created evaluator file: {evaluator_file}"
        if _HAS_RICH
        else f"✅ Created evaluator file: {evaluator_file}"
    )

    if config_path.exists():
        mapping = {"response": "model.response"}
        if add_evaluator_to_config(config_path, name, mapping=mapping):
            echo(
                f"[bold green]✅[/bold green] Updated {config_path}"
                if _HAS_RICH
                else f"✅ Updated {config_path}"
            )
        else:
            echo_error(f"Could not update {config_path}. Add the evaluator manually.")

    echo("\nNext steps:")
    echo(f"  1. Implement compute() and aggregate() in {evaluator_file}")
    echo("  2. Update the mapping in your config YAML")
    echo("  3. Run: ev run")


def _add_builtin_evaluator(name: str, config_path: Path, force: bool):
    """Add a built-in evaluator to config."""
    _HAS_RICH = has_rich()

    builtin_names = [e[0] for e in BUILTIN_EVALUATORS]
    if name not in builtin_names:
        echo_error(f"Unknown built-in evaluator: {name}")
        echo("\nUse 'ev evaluator builtins' to see available evaluators.")
        raise click.Abort()

    if not config_path.exists():
        echo_error(f"Config file not found: {config_path}")
        raise click.Abort()

    mapping = {"response": "model.response", "query": "dataset.query"}
    if add_evaluator_to_config(config_path, name, mapping=mapping):
        echo(
            f"[bold green]✅[/bold green] Added built-in evaluator '{name}' to {config_path}"
            if _HAS_RICH
            else f"✅ Added built-in evaluator '{name}' to {config_path}"
        )
    else:
        echo_error(f"Could not update {config_path}")

    echo("\nNext steps:")
    echo("  1. Update the mapping in your config YAML")
    echo("  2. Run: ev run")


@evaluator.command(name="builtins")
@click.help_option("--help", "-h")
def builtins_cmd():
    """Show available built-in evaluators."""
    _HAS_RICH = has_rich()

    echo(
        f"\n[bold cyan]Built-in Evaluators ({len(BUILTIN_EVALUATORS)}):[/bold cyan]\n"
        if _HAS_RICH
        else f"\nBuilt-in Evaluators ({len(BUILTIN_EVALUATORS)}):\n"
    )

    for eval_name, mode, description in BUILTIN_EVALUATORS:
        if _HAS_RICH:
            echo(f"  [yellow]{eval_name:<28}[/yellow] [blue]{mode:<8}[/blue] {description}")
        else:
            echo(f"  {eval_name:<28} {mode:<8} {description}")

    echo(f"\nAdd to your project: ev evaluator add --type {TEMPLATE_TYPE_BUILTIN} --name <name>")
