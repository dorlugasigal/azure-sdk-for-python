# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""discover command — scan project and show what's available."""
from __future__ import annotations

import json as json_mod
import os
import sys
from typing import Any, Dict, List

import click

from ..utils.constants import BUILTIN_EVALUATORS
from ..utils.discovery import import_local_components, discover_project_components
from ..utils.output import echo, has_rich, get_console


@click.command(name="discover")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON (for MCP integration)")
@click.help_option("--help", "-h")
def discover(output_json):
    """Discover available components — custom and built-in."""
    _console = get_console()
    _HAS_RICH = has_rich()

    # Discover from project files
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    import_local_components(cwd)
    found = discover_project_components()

    # JSON mode
    if output_json:
        result: Dict[str, Any] = {
            "targets": [{"name": n} for n in found["targets"]],
            "evaluators": {
                "custom": [{"name": n} for n in found["evaluators"]],
                "builtin": [{"name": n, "type": t, "description": d} for n, t, d in BUILTIN_EVALUATORS],
            },
            "datasets": [{"name": n} for n in found["datasets"]],
        }
        print(json_mod.dumps(result))
        return

    # --- Project Components ---
    echo(f"\n[bold underline]Project[/bold underline]" if _HAS_RICH else "\n── Project ──")

    # Targets
    echo(f"\n  [cyan]Targets:[/cyan]" if _HAS_RICH else "\n  Targets:")
    if found["targets"]:
        for name in found["targets"]:
            echo(f"    {name}")
    else:
        echo("    [dim](none)[/dim]" if _HAS_RICH else "    (none)")

    # Custom evaluators
    echo(f"\n  [cyan]Evaluators:[/cyan]" if _HAS_RICH else "\n  Evaluators:")
    if found["evaluators"]:
        for name in found["evaluators"]:
            echo(f"    {name}")
    else:
        echo("    [dim](none)[/dim]" if _HAS_RICH else "    (none)")

    # Datasets
    echo(f"\n  [cyan]Datasets:[/cyan]" if _HAS_RICH else "\n  Datasets:")
    if found["datasets"]:
        for name in found["datasets"]:
            echo(f"    {name}")
    else:
        echo("    [dim](none)[/dim]" if _HAS_RICH else "    (none)")

    # --- Built-in ---
    echo(f"\n[bold underline]Built-in[/bold underline]" if _HAS_RICH else "\n── Built-in ──")

    echo(f"\n  [cyan]Evaluators ({len(BUILTIN_EVALUATORS)}):[/cyan]" if _HAS_RICH else f"\n  Evaluators ({len(BUILTIN_EVALUATORS)}):")
    if _HAS_RICH:
        from rich.table import Table

        table = Table(border_style="dim", padding=(0, 2), show_header=True)
        table.add_column("Name", style="bold")
        table.add_column("Type", justify="center")
        table.add_column("Description")
        for name, etype, desc in BUILTIN_EVALUATORS:
            type_style = "[green]local[/green]" if etype == "local" else "[blue]cloud[/blue]"
            table.add_row(name, type_style, desc)
        _console.print(table)
    else:
        for name, etype, desc in BUILTIN_EVALUATORS:
            echo(f"    {name:<28} {etype:<8} {desc}")

    echo(f"\n  [cyan]Dataset types:[/cyan]  csv, jsonl" if _HAS_RICH else "\n  Dataset types:  csv, jsonl")

    echo("")
