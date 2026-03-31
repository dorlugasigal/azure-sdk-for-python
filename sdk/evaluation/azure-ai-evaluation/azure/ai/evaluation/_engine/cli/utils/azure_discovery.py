# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Azure resource discovery helpers shared by CLI commands."""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import click

from .output import echo, has_rich


# ---------------------------------------------------------------------------
# az CLI runner
# ---------------------------------------------------------------------------


def az_run(args: list[str]) -> dict | list | None:
    """Run an ``az`` CLI command and return parsed JSON output, or *None* on failure.

    Commands that produce no output (e.g. ``az account set``) return an empty dict
    on success.
    """
    try:
        result = subprocess.run(
            ["az", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Interactive selection menu
# ---------------------------------------------------------------------------


def select_option(prompt: str, options: list[tuple[str, str]], default: int = 0) -> int:
    """Arrow-key navigable selection menu. Returns chosen index.

    Each option is ``(label, hint)`` — *hint* is shown dimmed after the label.
    Falls back to numbered list when stdin is not a TTY.
    """
    # Fallback for non-TTY (piped input, CI, etc.)
    if not sys.stdin.isatty():
        echo(f"\n{prompt}")
        for i, (label, _) in enumerate(options):
            prefix = "(default) " if i == default else ""
            echo(f"  {i + 1}) {prefix}{label}")
        raw = click.prompt("Select", default=str(default + 1))
        return int(raw) - 1

    import termios
    import tty

    selected = default
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def _render():
        sys.stdout.write(f"\r\033[K  {prompt}\r\n")
        for i, (label, hint) in enumerate(options):
            if i == selected:
                line = f"\033[K    \033[36m❯ {label}\033[0m"
            else:
                line = f"\033[K      {label}"
            if hint:
                line += f"  \033[2m{hint}\033[0m"
            sys.stdout.write(line + "\r\n")
        sys.stdout.flush()

    try:
        tty.setraw(fd)
        sys.stdout.write("\r\n")
        _render()
        while True:
            ch = sys.stdin.read(1)
            if ch == "\r" or ch == "\n":
                break
            if ch == "\x03":  # Ctrl+C
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                sys.stdout.write(f"\033[{len(options) + 1}A")
                for _ in range(len(options) + 1):
                    sys.stdout.write("\033[K\n")
                sys.stdout.write(f"\033[{len(options) + 1}A")
                echo("  Cancelled.")
                raise SystemExit(0)
            if ch == "\x1b":  # escape sequence
                seq = sys.stdin.read(2)
                if seq == "[A":  # up
                    selected = (selected - 1) % len(options)
                elif seq == "[B":  # down
                    selected = (selected + 1) % len(options)
            sys.stdout.write(f"\033[{len(options) + 1}A")
            _render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    # Clear the menu and print the final selection
    sys.stdout.write(f"\033[{len(options) + 1}A")
    for _ in range(len(options) + 1):
        sys.stdout.write("\033[K\n")
    sys.stdout.write(f"\033[{len(options) + 1}A")
    echo(f"  {prompt} [cyan]{options[selected][0]}[/cyan]" if has_rich() else f"  {prompt} {options[selected][0]}")

    return selected


# ---------------------------------------------------------------------------
# Foundry project discovery
# ---------------------------------------------------------------------------


def discover_foundry_project() -> dict[str, str] | None:
    """Interactive Foundry project discovery via ``az`` CLI.

    Returns a dict with ``subscription_id``, ``resource_group``,
    ``project_name``, and ``endpoint``; or *None* if the user cancels
    or discovery fails.
    """
    # Check az CLI availability
    try:
        subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        az_available = True
    except Exception:
        az_available = False

    if not az_available:
        echo("  Azure CLI not found. Install it: https://aka.ms/install-az")
        echo("  Falling back to manual configuration.\n")
        sub_id = click.prompt("  Subscription ID", type=str)
        rg = click.prompt("  Resource Group", type=str)
        project = click.prompt("  Project Name", type=str)
        endpoint = click.prompt("  Endpoint URL", type=str)
        return {
            "subscription_id": sub_id.strip(),
            "resource_group": rg.strip(),
            "project_name": project.strip(),
            "endpoint": endpoint.strip(),
        }

    # --- az CLI is available ---
    echo("  Authenticating...")

    current_sub = az_run(["account", "show", "--query", "{name:name, id:id}", "-o", "json"])
    if not current_sub:
        echo("  Could not determine current Azure subscription.")
        return None

    echo(f"  Using subscription: [cyan]{current_sub['name']}[/cyan]" if has_rich() else f"  Using subscription: {current_sub['name']}")
    echo(f"  [dim](Change with: az account set --subscription <name>)[/dim]" if has_rich() else "  (Change with: az account set --subscription <name>)")

    projects = az_run([
        "resource", "list",
        "--resource-type", "Microsoft.CognitiveServices/accounts/projects",
        "--query", '[].{name:name, rg:resourceGroup, location:location, id:id}',
        "-o", "json",
    ])
    if not projects:
        echo("  No Foundry projects found in this subscription.")
        return None

    proj_options = [(p["name"], f'{p["rg"]} / {p["location"]}') for p in projects]
    proj_idx = select_option("Select Foundry project:", proj_options, default=0)
    selected_proj = projects[proj_idx]

    full_name = selected_proj["name"]
    if "/" in full_name:
        project_name = full_name.split("/", 1)[1]
    else:
        project_name = full_name

    parent_id = selected_proj["id"]
    if "/projects/" in parent_id:
        parent_id = parent_id[: parent_id.index("/projects/")]

    endpoint_info = az_run([
        "resource", "show",
        "--ids", parent_id,
        "--query", "{endpoint:properties.endpoint, foundryEndpoint:properties.endpoints.\"AI Foundry API\"}",
        "-o", "json",
    ])

    endpoint = ""
    if endpoint_info:
        # Prefer the AI Foundry API endpoint (required by AIProjectClient)
        endpoint = endpoint_info.get("foundryEndpoint") or endpoint_info.get("endpoint") or ""
    if not endpoint:
        echo("  Could not discover endpoint automatically.")
        endpoint = click.prompt("  Endpoint URL", type=str).strip()

    # Build project-scoped endpoint: AIProjectClient requires /api/projects/{name}
    endpoint = endpoint.rstrip("/")
    if "/api/projects/" not in endpoint:
        endpoint = f"{endpoint}/api/projects/{project_name}"

    account_name = full_name.split("/", 1)[0] if "/" in full_name else full_name
    deployments = az_run([
        "cognitiveservices", "account", "deployment", "list",
        "--name", account_name,
        "--resource-group", selected_proj["rg"],
        "--query", "[].{name:name, model:properties.model.name, version:properties.model.version}",
        "-o", "json",
    ])

    deployment_name = ""
    if deployments:
        dep_options = [(d["name"], f'{d.get("model", "")} {d.get("version", "")}') for d in deployments]
        dep_idx = select_option("Select model deployment:", dep_options, default=0)
        deployment_name = deployments[dep_idx]["name"]
    else:
        echo("  [dim]No deployments found — you can add one later.[/dim]" if has_rich() else "  No deployments found — you can add one later.")

    return {
        "subscription_id": current_sub["id"],
        "resource_group": selected_proj["rg"],
        "project_name": project_name,
        "endpoint": endpoint,
        "deployment": deployment_name,
    }
