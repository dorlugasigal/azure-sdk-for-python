# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""cloud command — configure Azure cloud settings for evaluation experiments.

Provides ``cloud set`` and ``cloud show`` subcommands for managing the
``cloud`` block in the project configuration (foundry endpoint, project,
default evaluator deployment, and App Insights).

``cloud set`` automatically discovers Azure AI resources via the ``az`` CLI
when invoked interactively, falling back to manual prompts when ``az`` is
unavailable or the user declines.  All options can also be passed as flags
for non-interactive / CI usage.
"""
from __future__ import annotations

import os
import shutil
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
# Helpers
# ---------------------------------------------------------------------------


def _check_az_cli() -> bool:
    """Return True if the ``az`` CLI is available on PATH."""
    return shutil.which("az") is not None


def _derive_foundry_endpoint(project_endpoint: str) -> str:
    """Derive the OpenAI-compatible endpoint from a project endpoint.

    Project endpoint: ``https://acct.services.ai.azure.com/api/projects/name``
    Foundry endpoint: ``https://acct.services.ai.azure.com/openai/v1``
    """
    api_projects_idx = project_endpoint.find("/api/projects/")
    if api_projects_idx != -1:
        return project_endpoint[:api_projects_idx] + "/openai/v1"
    return project_endpoint.rstrip("/") + "/openai/v1"


def _save_cloud_config(
    config: str,
    foundry_endpoint: str,
    foundry_project: str,
    default_deployment: str,
    app_insights: str,
) -> None:
    """Write the cloud section to the experiment config file."""
    if os.path.exists(config):
        cfg_data = load_yaml_ruamel(config)
        if cfg_data is None:
            cfg_data = {}
    else:
        cfg_data = {"experiment": {}}

    experiment = cfg_data.setdefault("experiment", {})

    cloud_section: dict = {
        "foundry_endpoint": foundry_endpoint,
        "default_evaluator_deployment_name": default_deployment,
    }
    if foundry_project:
        cloud_section["foundry_project"] = foundry_project
    if app_insights:
        cloud_section["app_insight"] = app_insights
    else:
        # Preserve existing app_insight if not being overwritten
        existing_cloud = experiment.get("cloud")
        if isinstance(existing_cloud, dict) and existing_cloud.get("app_insight"):
            cloud_section["app_insight"] = existing_cloud["app_insight"]

    experiment["cloud"] = cloud_section

    # Remove legacy compute block if it only had foundry config
    compute_cfg = experiment.get("compute")
    if isinstance(compute_cfg, dict) and compute_cfg.get("type") == "foundry":
        del experiment["compute"]

    write_yaml_ruamel(config, cfg_data)


def _print_summary(
    config: str,
    foundry_endpoint: str,
    foundry_project: str,
    default_deployment: str,
    app_insights: str,
) -> None:
    """Print the saved cloud configuration summary."""
    _console = get_console()
    _HAS_RICH = has_rich()

    if _HAS_RICH:
        _console.print(f"\n[green]✓[/green] Cloud configuration saved to [cyan]{config}[/cyan]")
        _console.print(f"  foundry_endpoint: {foundry_endpoint}")
        if foundry_project:
            _console.print(f"  foundry_project: {foundry_project}")
        _console.print(f"  default_evaluator_deployment_name: {default_deployment}")
        if app_insights:
            _console.print(f"  app_insight: (set)")
    else:
        click.echo(f"\n✓ Cloud configuration saved to {config}")
        click.echo(f"  foundry_endpoint: {foundry_endpoint}")
        if foundry_project:
            click.echo(f"  foundry_project: {foundry_project}")
        click.echo(f"  default_evaluator_deployment_name: {default_deployment}")
        if app_insights:
            click.echo(f"  app_insight: (set)")


def _interactive_discovery() -> tuple[str, str, str]:
    """Run Azure CLI discovery and return (foundry_endpoint, foundry_project, deployment).

    Returns empty strings for any value that could not be discovered.
    Raises ``SystemExit`` if the user cancels.
    """
    from ..utils.azure_discovery import discover_foundry_project

    result = discover_foundry_project()
    if result is None:
        echo_error("Discovery cancelled or failed.")
        sys.exit(1)

    project_endpoint = result.get("endpoint", "")
    deployment = result.get("deployment", "")
    foundry_endpoint = _derive_foundry_endpoint(project_endpoint) if project_endpoint else ""

    return foundry_endpoint, project_endpoint, deployment


def _manual_prompts(
    foundry_endpoint: str | None,
    foundry_project: str | None,
    default_deployment: str | None,
) -> tuple[str, str, str]:
    """Prompt the user for each cloud value manually."""
    _HAS_RICH = has_rich()

    if _HAS_RICH:
        echo("\n[dim]Enter cloud settings manually:[/dim]")
    else:
        echo("\nEnter cloud settings manually:")

    if not foundry_endpoint:
        foundry_endpoint = click.prompt(
            "  Foundry endpoint (must end with /openai/v1)", type=str
        ).strip()
    if not foundry_project:
        foundry_project = click.prompt(
            "  Foundry project endpoint (optional, press Enter to skip)",
            type=str,
            default="",
        ).strip()
    if not default_deployment:
        default_deployment = click.prompt(
            "  Default evaluator deployment",
            type=str,
            default="gpt-4.1-mini",
        ).strip()

    return foundry_endpoint, foundry_project, default_deployment


# ---------------------------------------------------------------------------
# cloud set
# ---------------------------------------------------------------------------


@cloud.command(name="set")
@click.option(
    "--foundry-endpoint",
    default=None,
    required=False,
    help="Azure OpenAI-compatible endpoint (must end with /openai/v1).",
)
@click.option(
    "--foundry-project",
    default=None,
    required=False,
    help="Azure AI Foundry project endpoint.",
)
@click.option(
    "--default-deployment",
    default=None,
    required=False,
    help="Default model deployment for cloud evaluators.",
)
@click.option(
    "--app-insights",
    default=None,
    required=False,
    help="Application Insights connection string (optional).",
)
@click.option("--config", "-c", default=None, help="Path to config file")
@click.help_option("--help", "-h")
def set_cloud(foundry_endpoint, foundry_project, default_deployment, app_insights, config):
    """Set cloud configuration for Azure AI evaluation.

    When invoked without flags, discovers Azure AI resources automatically
    via the ``az`` CLI.  Falls back to manual prompts when ``az`` is not
    available or the user declines discovery.

    All options can be passed as flags for non-interactive / CI usage.
    When all required flags (``--foundry-endpoint`` and
    ``--default-deployment``) are provided, interactive mode is skipped.

    \b
    Examples:
        ev cloud set
        ev cloud set --foundry-endpoint https://my.openai.azure.com/openai/v1
        ev cloud set --foundry-endpoint https://my.openai.azure.com/openai/v1 \\
                     --foundry-project https://my.ai.azure.com/project \\
                     --default-deployment gpt-4.1-mini
    """
    _HAS_RICH = has_rich()

    config = resolve_config_path(config)
    if not os.path.exists(config):
        echo_error(f"Config file '{config}' not found.")
        click.echo("Create a project first with: ev new <name>", err=True)
        sys.exit(1)

    # --- Non-interactive fast-path: all required flags provided -------------
    if foundry_endpoint and default_deployment:
        _save_cloud_config(
            config,
            foundry_endpoint,
            foundry_project or "",
            default_deployment,
            app_insights or "",
        )
        _print_summary(config, foundry_endpoint, foundry_project or "", default_deployment, app_insights or "")
        return

    # --- Interactive mode ----------------------------------------------------
    if _HAS_RICH:
        echo("\n🔍 Checking Azure CLI...")
    else:
        echo("\nChecking Azure CLI...")

    az_available = _check_az_cli()

    use_discovery = False
    if az_available:
        from ..utils.azure_discovery import az_run

        account = az_run(["account", "show", "--query", "{name:name, user:user.name}", "-o", "json"])
        if account:
            if _HAS_RICH:
                echo(
                    f"[green]✓[/green] Azure CLI detected. Signed in as "
                    f"[cyan]{account.get('user', 'unknown')}[/cyan] "
                    f"(subscription: [cyan]{account.get('name', 'unknown')}[/cyan])"
                )
            else:
                echo(
                    f"✓ Azure CLI detected. Signed in as "
                    f"{account.get('user', 'unknown')} "
                    f"(subscription: {account.get('name', 'unknown')})"
                )
            use_discovery = click.confirm(
                "\n? Discover Azure AI resources automatically?", default=True
            )
        else:
            echo("  Azure CLI found but not signed in. Falling back to manual input.")
    else:
        echo("  Azure CLI not found. Using manual input.")
        echo("  (Install from: https://aka.ms/installazurecli)")

    if use_discovery:
        discovered_endpoint, discovered_project, discovered_deployment = _interactive_discovery()
        # Allow flags to override discovered values
        foundry_endpoint = foundry_endpoint or discovered_endpoint
        foundry_project = foundry_project or discovered_project
        default_deployment = default_deployment or discovered_deployment
    else:
        foundry_endpoint, foundry_project, default_deployment = _manual_prompts(
            foundry_endpoint, foundry_project, default_deployment
        )

    # Ensure we have the required values
    if not foundry_endpoint:
        echo_error("Foundry endpoint is required.")
        sys.exit(1)
    if not default_deployment:
        default_deployment = "gpt-4.1-mini"

    # Prompt for app insights if not provided via flag
    if app_insights is None:
        app_insights = click.prompt(
            "\n? Application Insights connection string (optional, press Enter to skip)",
            type=str,
            default="",
        ).strip()

    _save_cloud_config(config, foundry_endpoint, foundry_project or "", default_deployment, app_insights or "")
    _print_summary(config, foundry_endpoint, foundry_project or "", default_deployment, app_insights or "")


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
