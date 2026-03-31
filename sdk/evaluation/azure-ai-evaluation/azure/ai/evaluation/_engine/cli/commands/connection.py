# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""connection command — manage custom model connections.

Provides ``connection list``, ``connection add``, and ``connection discover``
subcommands for viewing, creating, and auto-discovering custom Azure OpenAI
connections in the project configuration.

Note: For Azure AI service cloud settings (foundry endpoint, project, and
default evaluator deployment), use ``ev cloud`` instead.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Optional

import click
import yaml

from ..utils.constants import resolve_config_path
from ..utils.discovery import load_config_safe
from ..utils.output import echo, echo_error, has_rich, get_console, show_panel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_API_VERSION = "2024-12-01-preview"


def _load_yaml_raw(path: str) -> dict:
    """Load a YAML file as a plain dict."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml_ruamel(path: str, data) -> None:
    """Write *data* to *path* using ruamel.yaml to preserve comments.

    Falls back to PyYAML if ruamel is not installed.
    """
    try:
        from ruamel.yaml import YAML

        ry = YAML()
        ry.preserve_quotes = True  # type: ignore[assignment]
        with open(path, "w", encoding="utf-8") as f:
            ry.dump(data, f)
    except ImportError:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)


def _load_yaml_ruamel(path: str):
    """Load a YAML file using ruamel.yaml (preserves comments) or PyYAML."""
    try:
        from ruamel.yaml import YAML

        ry = YAML()
        with open(path, encoding="utf-8") as f:
            return ry.load(f)
    except ImportError:
        return _load_yaml_raw(path)


def _validate_connection_name(name: str) -> tuple[bool, str]:
    """Validate a connection name — alphanumeric, hyphens, or underscores."""
    if not name or not name.strip():
        return False, "Connection name cannot be empty."
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", name.strip()):
        return False, "Connection name must contain only alphanumeric characters, hyphens, or underscores."
    if len(name.strip()) > 100:
        return False, "Connection name is too long (max 100 characters)."
    return True, ""


def _get_connections(cfg_data: dict) -> list:
    """Extract the connections list from a raw config dict."""
    experiment = cfg_data.get("experiment", {}) or {}
    return experiment.get("connections", []) or []


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.option("--config", "-c", default=None, help="Path to config file")
@click.help_option("--help", "-h")
@click.pass_context
def connection(ctx, config):
    """Manage custom model connections.

    For Azure AI cloud settings (foundry endpoint, project, default deployment),
    use 'ev cloud' instead. This command is for managing additional custom
    connections to specific Azure OpenAI endpoints.
    """
    ctx.ensure_object(dict)
    config = resolve_config_path(config)
    ctx.obj["config"] = config
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ---------------------------------------------------------------------------
# connection list
# ---------------------------------------------------------------------------


@connection.command(name="list")
@click.option("--config", "-c", default=None, help="Path to config file")
@click.help_option("--help", "-h")
def list_connections(config):
    """Show configured connections from config.yaml."""
    _console = get_console()
    _HAS_RICH = has_rich()

    config = resolve_config_path(config)
    if not os.path.exists(config):
        echo_error(f"Config file '{config}' not found.")
        click.echo("Create a project first with: ev new <name>", err=True)
        sys.exit(1)

    cfg_data = _load_yaml_raw(config)
    connections = _get_connections(cfg_data)

    if not connections:
        echo("No connections configured.")
        click.echo("Add one with: ev connection add --name <name>")
        return

    if _HAS_RICH:
        from rich.table import Table

        table = Table(title="Connections", border_style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Endpoint")
        table.add_column("Deployment")
        table.add_column("API Version")

        for conn in connections:
            table.add_row(
                conn.get("name", "—"),
                conn.get("endpoint", "—"),
                conn.get("deployment", "—"),
                conn.get("api_version", "—"),
            )
        _console.print(table)
    else:
        click.echo("--- Connections ---")
        for conn in connections:
            click.echo(f"  {conn.get('name', '?')}:")
            click.echo(f"    endpoint:    {conn.get('endpoint', '—')}")
            click.echo(f"    deployment:  {conn.get('deployment', '—')}")
            click.echo(f"    api_version: {conn.get('api_version', '—')}")


# ---------------------------------------------------------------------------
# connection add
# ---------------------------------------------------------------------------


@connection.command(name="add")
@click.option("--name", "-n", required=True, help="Connection name")
@click.option("--endpoint", "-e", default=None, help="Endpoint URL")
@click.option("--deployment", "-d", default=None, help="Default deployment name")
@click.option("--api-version", default=_DEFAULT_API_VERSION, help="API version")
@click.option("--config", "-c", default=None, help="Path to config file")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing connection")
@click.help_option("--help", "-h")
def add_connection(name, endpoint, deployment, api_version, config, force):
    """Add a new connection to the project configuration.

    \b
    Examples:
        ev connection add -n my-conn -e https://my.openai.azure.com
        ev connection add -n prod --deployment gpt-4 --force
    """
    _console = get_console()
    _HAS_RICH = has_rich()

    # Validate name
    valid, err = _validate_connection_name(name)
    if not valid:
        echo_error(err)
        sys.exit(1)
    name = name.strip()

    config = resolve_config_path(config)
    if not os.path.exists(config):
        echo_error(f"Config file '{config}' not found.")
        click.echo("Create a project first with: ev new <name>", err=True)
        sys.exit(1)

    # Prompt for endpoint if not provided
    if not endpoint:
        endpoint = click.prompt("  Endpoint URL")

    # Load config (ruamel preserves comments)
    cfg_data = _load_yaml_ruamel(config)
    if cfg_data is None:
        cfg_data = {}

    experiment = cfg_data.setdefault("experiment", {})
    connections = experiment.setdefault("connections", [])

    # Check for duplicate
    existing_idx = None
    for i, conn in enumerate(connections):
        if isinstance(conn, dict) and conn.get("name") == name:
            existing_idx = i
            break

    if existing_idx is not None and not force:
        echo_error(f"Connection '{name}' already exists. Use --force to overwrite.")
        sys.exit(1)

    new_conn = {"name": name, "api_version": api_version}
    if endpoint:
        new_conn["endpoint"] = endpoint
    if deployment:
        new_conn["deployment"] = deployment

    if existing_idx is not None:
        connections[existing_idx] = new_conn
    else:
        connections.append(new_conn)

    _write_yaml_ruamel(config, cfg_data)

    if _HAS_RICH:
        _console.print(f"[green]✓[/green] Connection [cyan]{name}[/cyan] added to {config}")
    else:
        click.echo(f"✓ Connection '{name}' added to {config}")


# ---------------------------------------------------------------------------
# connection discover
# ---------------------------------------------------------------------------


def _check_az_cli() -> bool:
    """Return True if the ``az`` CLI is available on PATH."""
    return shutil.which("az") is not None


def _list_deployments(account: str, resource_group: str) -> list[dict]:
    """List model deployments from an Azure Cognitive Services account."""
    cmd = [
        "az", "cognitiveservices", "account", "deployment", "list",
        "--name", account,
        "--resource-group", resource_group,
        "-o", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"az command failed (exit {result.returncode})")
    return json.loads(result.stdout)


@connection.command(name="discover")
@click.option("--config", "-c", default=None, help="Path to config file")
@click.help_option("--help", "-h")
def discover_connections(config):
    """Discover model deployments from your Azure AI Foundry project.

    Auto-detects account and resource group from .env or prompts
    for Foundry project selection if not configured.

    \b
    Examples:
        ev connection discover
    """
    _console = get_console()
    _HAS_RICH = has_rich()

    config = resolve_config_path(config)

    if not _check_az_cli():
        echo_error("Azure CLI (az) is not installed or not on PATH.")
        click.echo("\nInstall it from: https://aka.ms/installazurecli")
        click.echo("Or add a connection manually: ev connection add -n <name> -e <endpoint>")
        sys.exit(1)

    # Try to auto-detect account and resource group from .env
    account = None
    resource_group = None
    endpoint = None

    # Load .env if it exists
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_path, override=True)
        except ImportError:
            # Read .env manually
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())

    resource_group = os.environ.get("AZURE_RESOURCE_GROUP")
    project_endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")

    # Try to extract account name from endpoint or project name
    project_name_env = os.environ.get("AZURE_AI_PROJECT_NAME")
    if project_endpoint:
        # endpoint like https://account.services.ai.azure.com/
        import re
        m = re.match(r"https://([^.]+)\.", project_endpoint)
        if m:
            account = m.group(1)
            endpoint = project_endpoint

    if not account or not resource_group:
        # Fall back to Foundry project discovery via az CLI
        echo("  No Foundry project configured in .env — discovering...")
        from ..utils.azure_discovery import az_run as _az_run, select_option as _select_option

        projects = _az_run([
            "resource", "list",
            "--resource-type", "Microsoft.CognitiveServices/accounts/projects",
            "--query", "[].{name:name, rg:resourceGroup, location:location, id:id}",
            "-o", "json",
        ])
        if not projects:
            echo("  No Foundry projects found. Create one at https://ai.azure.com")
            sys.exit(1)

        proj_options = [(p["name"], f'{p["rg"]} / {p["location"]}') for p in projects]
        proj_idx = _select_option("Select Foundry project:", proj_options, default=0)
        selected = projects[proj_idx]

        full_name = selected["name"]
        account = full_name.split("/", 1)[0] if "/" in full_name else full_name
        resource_group = selected["rg"]

        # Get endpoint from parent account
        parent_id = selected["id"]
        if "/projects/" in parent_id:
            parent_id = parent_id[:parent_id.index("/projects/")]
        endpoint_info = _az_run(["resource", "show", "--ids", parent_id, "--query", "{endpoint:properties.endpoint}", "-o", "json"])
        if endpoint_info and endpoint_info.get("endpoint"):
            endpoint = endpoint_info["endpoint"]

    echo(f"  Account: [cyan]{account}[/cyan]" if _HAS_RICH else f"  Account: {account}")
    echo(f"  Resource group: [cyan]{resource_group}[/cyan]" if _HAS_RICH else f"  Resource group: {resource_group}")

    try:
        deployments = _list_deployments(account, resource_group)
    except RuntimeError as exc:
        echo_error(f"Failed to list deployments: {exc}")
        sys.exit(1)

    if not deployments:
        click.echo("  No deployments found for this account.")
        return

    # Display deployments
    options = []
    for dep in deployments:
        dep_name = dep.get("name", "unknown")
        model_info = dep.get("properties", {}).get("model", {})
        model_name = model_info.get("name", "")
        model_version = model_info.get("version", "")
        hint = f"{model_name} {model_version}".strip() if model_name else ""
        options.append((dep_name, hint))

    if _HAS_RICH:
        from rich.table import Table
        table = Table(title="Available Deployments", border_style="cyan")
        table.add_column("Deployment", style="bold")
        table.add_column("Model")
        for label, hint in options:
            table.add_row(label, hint)
        _console.print(table)
    else:
        click.echo("\nAvailable Deployments:")
        for label, hint in options:
            click.echo(f"  {label}  {hint}")

    # Ask if user wants to create a connection
    if not click.confirm("\n  Create a connection from a deployment?", default=True):
        return

    from azure.ai.evaluation._engine.cli.commands.new import _select_option
    dep_idx = _select_option("Select deployment:", options, default=0)
    selected_dep = deployments[dep_idx]
    dep_name = selected_dep.get("name", "unknown")

    conn_name = click.prompt("  Connection name", default=dep_name)
    valid, err = _validate_connection_name(conn_name)
    if not valid:
        echo_error(err)
        sys.exit(1)

    conn_endpoint = endpoint or f"https://{account}.services.ai.azure.com"

    # Write to config
    if os.path.exists(config):
        cfg_data = _load_yaml_ruamel(config)
        if cfg_data is None:
            cfg_data = {}
    else:
        cfg_data = {"experiment": {}}

    experiment = cfg_data.setdefault("experiment", {})
    connections = experiment.setdefault("connections", [])

    new_conn = {
        "name": conn_name,
        "deployment": dep_name,
        "api_version": _DEFAULT_API_VERSION,
        "endpoint": conn_endpoint,
    }
    connections.append(new_conn)
    _write_yaml_ruamel(config, cfg_data)

    if _HAS_RICH:
        _console.print(f"\n[green]✓[/green] Connection [cyan]{conn_name}[/cyan] ({dep_name}) added to {config}")
    else:
        click.echo(f"\n✓ Connection '{conn_name}' ({dep_name}) added to {config}")
