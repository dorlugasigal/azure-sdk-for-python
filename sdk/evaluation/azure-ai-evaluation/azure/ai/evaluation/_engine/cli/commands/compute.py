# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""compute command — manage compute backend configuration.

Provides ``compute show`` and ``compute set`` subcommands.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import click

from ..utils.constants import resolve_config_path
from ..utils.discovery import load_config_safe
from ..utils.output import echo_error, has_rich, get_console, show_panel


@click.group(invoke_without_command=True)
@click.option("--config", "-c", default=None, help="Path to config file")
@click.help_option("--help", "-h")
@click.pass_context
def compute(ctx, config):
    """Manage compute backend configuration."""
    ctx.ensure_object(dict)
    config = resolve_config_path(config)
    ctx.obj["config"] = config
    # If invoked without subcommand, show current config (backward-compat)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@compute.command(name="show")
@click.option("--config", "-c", default=None, help="Path to config file")
@click.help_option("--help", "-h")
def show_backend(config):
    """Show current compute backend configuration."""
    config = resolve_config_path(config)
    if not os.path.exists(config):
        echo_error(f"Config file '{config}' not found.")
        sys.exit(1)

    cfg = load_config_safe(config)
    if cfg is None:
        echo_error(f"Failed to parse '{config}'.")
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

    show_panel(info, title="Compute Backend")


def _update_compute_in_config(config_path: str, backend: str, azure_ai_project: str | None = None) -> bool:
    """Update the compute section in the config YAML file.

    Returns ``True`` on success, ``False`` on failure.
    """
    try:
        from ruamel.yaml import YAML

        yaml_rt = YAML()
        yaml_rt.preserve_quotes = True  # type: ignore[assignment]

        with open(config_path, encoding="utf-8") as f:
            data = yaml_rt.load(f)
        if data is None:
            data = {}

        experiment = data.setdefault("experiment", {})

        # Build new compute section
        compute_section: dict = {"type": backend}
        if backend == "foundry" and azure_ai_project:
            compute_section["azure_ai_project"] = azure_ai_project

        experiment["compute"] = compute_section

        # Remove legacy key if present
        experiment.pop("compute_backend", None)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml_rt.dump(data, f)
        return True
    except Exception:
        return False


@compute.command(name="set")
@click.argument("backend", type=click.Choice(["local", "foundry"]))
@click.option("--config", "-c", default=None, help="Path to config file")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing configuration without prompting")
@click.help_option("--help", "-h")
def set_backend(backend, config, force):
    """Set the compute backend for experiments.

    BACKEND: The compute backend to use (local, foundry)

    \b
    Examples:
        ev compute set local       # Use local compute
        ev compute set foundry     # Configure Foundry cloud compute
    """
    _console = get_console()
    _HAS_RICH = has_rich()

    config = resolve_config_path(config)
    if not os.path.exists(config):
        echo_error(f"Config file '{config}' not found.")
        click.echo("Create a project first with: ev new <name>", err=True)
        sys.exit(1)

    cfg = load_config_safe(config)
    if cfg is None:
        echo_error(f"Failed to parse '{config}'.")
        sys.exit(1)

    # Check for existing config
    existing = getattr(cfg.experiment, "compute", None)
    existing_type = getattr(existing, "type", None) if existing else None

    if existing_type and existing_type != "local" and not force:
        if not click.confirm(f"Compute already set to '{existing_type}'. Overwrite?", default=False):
            click.echo("Cancelled.")
            return

    # Determine azure_ai_project for foundry backend
    azure_ai_project = None
    if backend == "foundry":
        # Always run interactive discovery so user picks the right project
        if sys.stdin.isatty():
            try:
                from ..utils.azure_discovery import discover_foundry_project

                foundry_info = discover_foundry_project()
                if foundry_info and foundry_info.get("endpoint"):
                    azure_ai_project = foundry_info["endpoint"]
            except Exception:
                pass

        # Fall back to existing config or env var
        if not azure_ai_project:
            existing_project = getattr(existing, "azure_ai_project", None) if existing else None
            azure_ai_project = existing_project or os.environ.get("AZURE_AI_PROJECT_ENDPOINT")

        # Normalize legacy endpoints
        if azure_ai_project:
            from azure.ai.evaluation._engine.foundry_compute import _normalize_endpoint
            azure_ai_project = _normalize_endpoint(azure_ai_project)

    # Write the compute section to the config file
    if not _update_compute_in_config(config, backend, azure_ai_project):
        echo_error(f"Could not update '{config}'.")
        click.echo("\nUpdate the compute section in your config manually:", err=True)
        click.echo("  compute:", err=True)
        click.echo(f'    type: "{backend}"', err=True)
        sys.exit(1)

    if _HAS_RICH:
        _console.print(f"[green]✓[/green] Compute backend set to [cyan]{backend}[/cyan]")
    else:
        click.echo(f"✓ Compute backend set to {backend}")

    if backend == "foundry":
        if not azure_ai_project:
            click.echo("\nSet 'compute.azure_ai_project' in your config or "
                        "export AZURE_AI_PROJECT_ENDPOINT to configure the Foundry endpoint.")
        # Check if azure-ai-projects is installed
        if importlib.util.find_spec("azure.ai.projects") is None:
            click.echo("\nNote: Foundry compute requires 'azure-ai-projects'. "
                        "Install with: pip install azure-ai-projects")
        click.echo("\nRun experiments with: ev run --remote")
    else:
        click.echo("\nRun experiments with: ev run")
