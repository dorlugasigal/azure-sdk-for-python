# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Rich output helpers with graceful fallback to plain click.echo."""
from __future__ import annotations

from typing import Any, Dict

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
    Table = None  # type: ignore[assignment,misc]
    Panel = None  # type: ignore[assignment,misc]
    Syntax = None  # type: ignore[assignment,misc]


def get_console():
    """Return the Rich console instance (or None if Rich is not available)."""
    return _console


def has_rich() -> bool:
    """Return True if Rich is available."""
    return _HAS_RICH


def echo(msg: str = "", *, err: bool = False) -> None:
    """Print a message using Rich if available, otherwise click.echo."""
    if _HAS_RICH:
        (_err_console if err else _console).print(msg)
    else:
        click.echo(msg, err=err)


def echo_error(msg: str) -> None:
    """Print an error message."""
    if _HAS_RICH:
        _err_console.print(f"[bold red]Error:[/bold red] {msg}")
    else:
        click.echo(f"Error: {msg}", err=True)


def show_panel(lines: Dict[str, str], *, title: str = "ev") -> None:
    """Display a key/value summary as a Rich Panel or plain text."""
    if _HAS_RICH:
        max_key = max(len(k) for k in lines)
        body = "\n".join(f"[bold]{k + ':':<{max_key + 1}}[/bold] {v}" for k, v in lines.items())
        _console.print(Panel(body, title=title, border_style="cyan", expand=False))
    else:
        click.echo(f"--- {title} ---")
        for k, v in lines.items():
            click.echo(f"  {k}: {v}")


def show_results_table(results: Dict[str, Any]) -> None:
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
