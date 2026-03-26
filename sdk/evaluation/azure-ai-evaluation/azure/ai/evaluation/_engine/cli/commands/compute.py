# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""compute command — manage compute backend configuration.

Provides ``compute show`` and ``compute set`` subcommands.
"""
from __future__ import annotations

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

    if _HAS_RICH:
        _console.print(f"[green]✓[/green] Compute backend set to [cyan]{backend}[/cyan]")
    else:
        click.echo(f"✓ Compute backend set to {backend}")

    if backend == "foundry":
        click.echo("\nConfigure 'compute.azure_ai_project' in your config to set the Foundry endpoint.")
        click.echo("Then run: ev run --remote")
    else:
        click.echo("\nRun experiments with: ev run")
