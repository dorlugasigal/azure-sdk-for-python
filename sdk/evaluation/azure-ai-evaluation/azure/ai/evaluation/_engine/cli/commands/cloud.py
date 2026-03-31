# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""cloud command — configure Azure cloud settings for evaluation experiments.

Provides ``cloud set`` and ``cloud show`` subcommands for managing
the ``cloud`` block in the project configuration (foundry endpoint,
project, default evaluator deployment, and App Insights).
"""
from __future__ import annotations

import os
import sys

import click
import yaml

from ..utils.constants import resolve_config_path
from ..utils.output import echo, echo_error, has_rich, get_console, show_panel
from ..utils.yaml_helpers import load_yaml_ruamel, write_yaml_ruamel


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.option("--config", "-c", default=None, help="Path to config file")
@click.help_option("--help", "-h")
@click.pass_context
def cloud(ctx, config):
    """Configure cloud settings for Azure AI evaluation."""
    ctx.ensure_object(dict)
    config = resolve_config_path(config)
    ctx.obj["config"] = config
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ---------------------------------------------------------------------------
# cloud set
# ---------------------------------------------------------------------------


@cloud.command(name="set")
@click.option(
    "--foundry-endpoint",
    prompt="Foundry endpoint (must end with /openai/v1)",
    help="Azure OpenAI-compatible endpoint (must end with /openai/v1).",
)
@click.option(
    "--foundry-project",
    prompt="Foundry project endpoint",
    default="",
    help="Azure AI Foundry project endpoint.",
)
@click.option(
    "--default-deployment",
    prompt="Default evaluator deployment",
    default="gpt-4.1-mini",
    help="Default model deployment for cloud evaluators.",
)
@click.option(
    "--app-insights",
    default="",
    help="Application Insights connection string (optional).",
)
@click.option("--config", "-c", default=None, help="Path to config file")
@click.help_option("--help", "-h")
def set_cloud(foundry_endpoint, foundry_project, default_deployment, app_insights, config):
    """Set cloud configuration in the experiment config.

    \b
    Examples:
        ev cloud set --foundry-endpoint https://my.openai.azure.com/openai/v1
        ev cloud set --foundry-endpoint https://my.openai.azure.com/openai/v1 \\
                     --foundry-project https://my.ai.azure.com/project \\
                     --default-deployment gpt-4.1-mini
    """
    _console = get_console()
    _HAS_RICH = has_rich()

    config = resolve_config_path(config)
    if not os.path.exists(config):
        echo_error(f"Config file '{config}' not found.")
        click.echo("Create a project first with: ev new <name>", err=True)
        sys.exit(1)

    # Load config (ruamel preserves comments)
    cfg_data = load_yaml_ruamel(config)
    if cfg_data is None:
        cfg_data = {}

    experiment = cfg_data.setdefault("experiment", {})

    # Build cloud section
    cloud_section: dict = {
        "foundry_endpoint": foundry_endpoint,
        "default_evaluator_deployment_name": default_deployment,
    }
    if foundry_project:
        cloud_section["foundry_project"] = foundry_project
    if app_insights:
        cloud_section["app_insight"] = app_insights

    experiment["cloud"] = cloud_section

    # Remove legacy compute block if it only had foundry config
    compute_cfg = experiment.get("compute")
    if isinstance(compute_cfg, dict) and compute_cfg.get("type") == "foundry":
        del experiment["compute"]

    write_yaml_ruamel(config, cfg_data)

    if _HAS_RICH:
        _console.print(f"[green]✓[/green] Cloud configuration saved to [cyan]{config}[/cyan]")
        _console.print(f"  foundry_endpoint: {foundry_endpoint}")
        if foundry_project:
            _console.print(f"  foundry_project: {foundry_project}")
        _console.print(f"  default_evaluator_deployment_name: {default_deployment}")
        if app_insights:
            _console.print(f"  app_insight: (set)")
    else:
        click.echo(f"✓ Cloud configuration saved to {config}")
        click.echo(f"  foundry_endpoint: {foundry_endpoint}")
        if foundry_project:
            click.echo(f"  foundry_project: {foundry_project}")
        click.echo(f"  default_evaluator_deployment_name: {default_deployment}")
        if app_insights:
            click.echo(f"  app_insight: (set)")


# ---------------------------------------------------------------------------
# cloud show
# ---------------------------------------------------------------------------


@cloud.command(name="show")
@click.option("--config", "-c", default=None, help="Path to config file")
@click.help_option("--help", "-h")
def show_cloud(config):
    """Show current cloud configuration."""
    config = resolve_config_path(config)
    if not os.path.exists(config):
        echo_error(f"Config file '{config}' not found.")
        sys.exit(1)

    with open(config, encoding="utf-8") as f:
        cfg_data = yaml.safe_load(f) or {}

    experiment = cfg_data.get("experiment", {}) or {}
    cloud_cfg = experiment.get("cloud")

    if not cloud_cfg:
        echo("No cloud configuration found.")
        click.echo("Set one with: ev cloud set")
        return

    info = {}
    for key in ("foundry_endpoint", "foundry_project", "default_evaluator_deployment_name", "app_insight"):
        val = cloud_cfg.get(key)
        if val:
            info[key] = val

    show_panel(info, title="Cloud Configuration")
