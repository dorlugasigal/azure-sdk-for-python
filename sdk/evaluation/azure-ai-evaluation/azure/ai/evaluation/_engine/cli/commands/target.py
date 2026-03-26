# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""target command group — discover, add, and list evaluation targets."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from ..utils.constants import resolve_config_path
from ..utils.discovery import import_local_components, discover_project_components
from ..utils.output import echo, echo_error, has_rich


DEFAULT_CONFIG = "config.yaml"


# ---------------------------------------------------------------------------
# Config helpers (previously in model.py)
# ---------------------------------------------------------------------------


def read_targets_from_config(config_path: Path) -> List[Dict[str, Any]]:
    """Read target configurations from the YAML config file.

    Supports both ``targets`` and the legacy ``models`` key.
    """
    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return []

    if not data or "experiment" not in data:
        return []

    experiment = data["experiment"]
    targets = experiment.get("targets", experiment.get("models", []))
    return targets if targets else []


def target_exists_in_config(config_path: Path, name: str) -> bool:
    """Return ``True`` if a target with *name* is already in the config."""
    return any(t.get("name") == name for t in read_targets_from_config(config_path))


def add_target_to_config(
    config_path: Path,
    name: str,
    target_type: str = "custom",
    connection_name: str = "default",
    args: Optional[Dict[str, Any]] = None,
) -> bool:
    """Add or replace a target entry in the config YAML file.

    Returns ``True`` on success, ``False`` on failure.
    """
    try:
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.preserve_quotes = True  # type: ignore[assignment]

        with open(config_path, encoding="utf-8") as f:
            data = yaml.load(f)
        if data is None:
            data = {}

        experiment = data.setdefault("experiment", {})

        # Prefer "targets" key; fall back to "models" if already present
        if "targets" not in experiment and "models" in experiment:
            targets_key = "models"
        else:
            targets_key = "targets"

        targets = experiment.setdefault(targets_key, [])

        entry: Dict[str, Any] = {
            "name": name,
            "type": target_type,
            "connection_name": connection_name,
            "args": args if args else {"temperature": [0.7]},
        }

        # Replace existing entry with same name, or append
        replaced = False
        for i, t in enumerate(targets):
            if isinstance(t, dict) and t.get("name") == name:
                targets[i] = entry
                replaced = True
                break
        if not replaced:
            targets.append(entry)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        return True
    except Exception:
        return False


@click.group(invoke_without_command=True)
@click.pass_context
def target_cmd(ctx):
    """Manage evaluation targets — add or list configured and discovered targets."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@target_cmd.command()
@click.option("--name", "-n", default=None, help="Name for the target (defaults to 'my_target').")
@click.option(
    "--type",
    "-t",
    "target_type",
    default="custom",
    type=click.Choice(["custom", "azure_ai_model", "azure_ai_agent"]),
    help="Target type (default: custom).",
)
@click.option(
    "--config",
    "-c",
    default=None,
    help="Path to config file (default: config.yaml).",
    type=click.Path(),
)
@click.option("--force", "-F", is_flag=True, help="Overwrite existing target configuration.")
@click.help_option("--help", "-h")
def add(name, target_type, config, force):
    """Add a new target configuration to the project config.

    Examples:\n
      ev target add --name my_target\n
      ev target add --name gpt4 --type azure_ai_model\n
      ev target add --name my_target --force
    """
    _HAS_RICH = has_rich()
    config = resolve_config_path(config)
    config_path = Path(config)

    if not config_path.exists():
        echo_error(f"Config file not found: {config_path}")
        echo("Make sure you're in the project directory or use --config to specify the path.")
        raise click.Abort()

    if not name:
        name = click.prompt("Enter a name for the target", default="my_target")

    if not force and target_exists_in_config(config_path, name):
        echo_error(f"Target '{name}' already exists in config. Use --force to overwrite.")
        raise click.Abort()

    if add_target_to_config(config_path, name, target_type=target_type):
        echo(
            f"[bold green]✅[/bold green] Target '{name}' added to {config_path}"
            if _HAS_RICH
            else f"✅ Target '{name}' added to {config_path}"
        )
        echo("\nNext steps:")
        echo("  1. Update the target configuration in your config YAML")
        echo("  2. Run your evaluation with: ev run")
    else:
        echo_error(f"Could not update {config_path}")
        echo("\nAdd this to your config manually:")
        echo("  targets:")
        echo(f'    - name: "{name}"')
        echo(f'      type: "{target_type}"')
        echo("      args:")
        echo("        temperature: [0.7]")


@target_cmd.command(name="list")
@click.argument("name", required=False)
@click.option(
    "--config",
    "-c",
    default=None,
    help="Path to config file (default: config.yaml).",
    type=click.Path(),
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed target information.")
@click.help_option("--help", "-h")
def list_targets(name, config, verbose):
    """List configured and discovered targets, or show details for a specific target.

    Without a name, displays both configured targets (from the config YAML)
    and discovered targets (from @target decorated classes).

    With a name, shows detailed information for that specific target.

    Examples:\n
      ev target list\n
      ev target list my_target\n
      ev target list --verbose\n
      ev target list --config path/to/config.yaml
    """
    _HAS_RICH = has_rich()

    # --- Read configured targets from YAML -----------------------------------
    config = resolve_config_path(config)
    config_path = Path(config)
    config_exists = config_path.exists()
    configured_targets = read_targets_from_config(config_path) if config_exists else []
    configured_names = {t.get("name") for t in configured_targets if isinstance(t, dict)}

    # --- Discover decorated targets ------------------------------------------
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    import_local_components(cwd)
    found = discover_project_components()
    discovered_names: List[str] = found.get("targets", [])

    # ---- Single-target detail mode ------------------------------------------
    if name:
        in_config = name in configured_names
        in_discovered = name in discovered_names

        if not in_config and not in_discovered:
            echo_error(f"Target '{name}' not found in config or decorator registry.")
            all_names = sorted(configured_names | set(discovered_names))
            if all_names:
                echo(f"Available targets: {', '.join(all_names)}")
            sys.exit(1)

        if in_config:
            cfg = next(t for t in configured_targets if t.get("name") == name)
            echo(
                f"\n[bold cyan]Configured Target:[/bold cyan] [green]{name}[/green]"
                if _HAS_RICH
                else f"\nConfigured Target: {name}"
            )
            for key, value in cfg.items():
                if key != "name":
                    echo(f"  {key}: {value}")

        if in_discovered:
            echo(
                f"[bold green]✓[/bold green] Target '{name}' is registered (discovered via @target decorator)."
                if _HAS_RICH
                else f"✓ Target '{name}' is registered (discovered via @target decorator)."
            )

        if in_config and not in_discovered:
            echo("\nNote: this target is configured but not discovered via decorators.")
        elif not in_config and in_discovered:
            echo("\nNote: this target is discovered via decorators but not in the config file.")
        return

    # ---- Full list mode (no name given) -------------------------------------
    has_any = bool(configured_targets) or bool(discovered_names)

    # Configured targets section
    if configured_targets:
        echo(
            f"\n[bold cyan]Configured Targets ({len(configured_targets)}):[/bold cyan]\n"
            if _HAS_RICH
            else f"\nConfigured Targets ({len(configured_targets)}):\n"
        )
        for i, target_config in enumerate(configured_targets, start=1):
            t_name = target_config.get("name", "unknown")
            also_discovered = t_name in discovered_names
            suffix = ""
            if also_discovered:
                suffix = (
                    " [dim](also discovered)[/dim]" if _HAS_RICH else " (also discovered)"
                )
            if verbose:
                echo(
                    f"{i}. [green]{t_name}[/green]{suffix}"
                    if _HAS_RICH
                    else f"{i}. {t_name}{suffix}"
                )
                for key, value in target_config.items():
                    if key != "name":
                        echo(f"   {key}: {value}")
                echo("")
            else:
                echo(
                    f"{i}. [green]{t_name}[/green]{suffix}"
                    if _HAS_RICH
                    else f"{i}. {t_name}{suffix}"
                )
        if not verbose:
            echo("\nUse --verbose to see full configuration details.")
    elif config_exists:
        echo("\nNo targets configured in your project config.")
    else:
        echo(f"\nConfig file not found: {config_path}")

    # Discovered targets section
    if discovered_names:
        echo(
            f"\n[bold cyan]Discovered Targets ({len(discovered_names)}):[/bold cyan]\n"
            if _HAS_RICH
            else f"\nDiscovered Targets ({len(discovered_names)}):\n"
        )
        for m in discovered_names:
            also_configured = m in configured_names
            suffix = ""
            if also_configured:
                suffix = (
                    " [dim](also configured)[/dim]" if _HAS_RICH else " (also configured)"
                )
            echo(f"  {m}{suffix}")
    else:
        echo("\nNo targets discovered via @target decorators.")

    if not has_any:
        echo("\nGet started:")
        echo("  • Add a target to your config:  ev target add --name my_target")
        echo("  • Or add a @target decorated class to your project.")
