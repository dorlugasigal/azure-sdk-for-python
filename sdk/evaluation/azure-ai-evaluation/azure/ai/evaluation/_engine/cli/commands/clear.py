# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""clear command — clean experiment output folders."""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from typing import List, Optional

import click

from ..utils.discovery import dir_size_str
from ..utils.output import echo, echo_error, has_rich, get_console


def _parse_folder_timestamp(name: str) -> Optional[datetime]:
    """Try to parse a timestamp from a folder name (e.g. ``2025-01-15_14-30-00``)."""
    for fmt in ("%Y-%m-%d_%H-%M-%S", "%Y%m%d_%H%M%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(name[:len(fmt.replace("%", "0"))], fmt)
        except (ValueError, IndexError):
            continue
    # Fall back to mtime
    return None


def _get_folder_datetime(path: str, name: str) -> datetime:
    """Return a datetime for sorting — parsed from name or mtime."""
    dt = _parse_folder_timestamp(name)
    if dt is not None:
        return dt
    try:
        return datetime.fromtimestamp(os.path.getmtime(os.path.join(path, name)))
    except OSError:
        return datetime.min


@click.command()
@click.option("--path", "-p", default="output", help="Output directory to clean")
@click.option("--config", "-c", default=None, help="Config file (reads output_path if --path not set)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.option("--preview", "-r", is_flag=True, help="Preview what would be deleted without deleting")
@click.option("--keep-last", "-k", type=click.IntRange(min=0), default=0, help="Keep N most recent experiment runs")
@click.option("--before", "-b", type=str, default=None, help="Remove experiments before date (YYYY-MM-DD)")
@click.option("--after", "-a", type=str, default=None, help="Remove experiments after date (YYYY-MM-DD)")
@click.option("--logs-only", "-l", is_flag=True, help="Clear only logs subdirectories, preserve results")
@click.help_option("--help", "-h")
def clear(path, config, force, preview, keep_last, before, after, logs_only):
    """Clear experiment output folders.

    Supports filtering by date range and keeping recent experiments.

    \b
    Examples:
        ev clear                          # Clear all output
        ev clear --keep-last 3            # Keep 3 most recent runs
        ev clear --logs-only              # Only remove logs/ dirs
        ev clear --before 2025-01-01      # Clear runs before a date
        ev clear --preview                # Dry-run preview
    """
    _console = get_console()
    _HAS_RICH = has_rich()

    # If --path was not explicitly changed from default, try reading from config.
    if path == "output":
        # Auto-detect config file if not specified
        if config is None:
            for candidate in ("config.yaml", "evals.yaml", "experiment/config.yaml"):
                if os.path.exists(candidate):
                    config = candidate
                    break
        if config and os.path.exists(config):
            try:
                from ..utils.discovery import load_config_safe
                cfg = load_config_safe(config)
                if cfg:
                    configured_path = getattr(cfg.experiment, "output_path", None)
                    if configured_path:
                        path = configured_path
            except Exception:
                pass
        # Fall back to legacy path if new default doesn't exist
        if not os.path.isdir(path) and os.path.isdir("experiment/output"):
            path = "experiment/output"

    if not os.path.isdir(path):
        echo_error(f"Directory '{path}' does not exist.")
        sys.exit(1)

    # Parse date filters
    before_date: Optional[datetime] = None
    after_date: Optional[datetime] = None
    try:
        if before:
            before_date = datetime.strptime(before, "%Y-%m-%d")
        if after:
            after_date = datetime.strptime(after, "%Y-%m-%d")
    except ValueError as e:
        echo_error(f"Invalid date format: {e}. Use YYYY-MM-DD.")
        sys.exit(1)

    subdirs = sorted(
        [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))],
        key=lambda d: _get_folder_datetime(path, d),
    )

    if not subdirs:
        echo("No output folders to clear.")
        return

    # Apply date filters
    if before_date or after_date:
        filtered: List[str] = []
        for d in subdirs:
            dt = _get_folder_datetime(path, d)
            if before_date and dt >= before_date:
                continue
            if after_date and dt <= after_date:
                continue
            filtered.append(d)
        subdirs = filtered

    # Apply --keep-last: preserve the N most recent
    if keep_last > 0 and len(subdirs) > keep_last:
        subdirs = subdirs[:-keep_last]
    elif keep_last > 0:
        echo(f"Only {len(subdirs)} folder(s) found, keeping all (--keep-last {keep_last}).")
        return

    if not subdirs:
        echo("No folders match the given filters.")
        return

    # For --logs-only, find logs/ subdirectories within each experiment folder
    if logs_only:
        logs_dirs: List[str] = []
        for d in subdirs:
            logs_path = os.path.join(path, d, "logs")
            if os.path.isdir(logs_path):
                logs_dirs.append(os.path.join(path, d, "logs"))
        if not logs_dirs:
            echo("No logs subdirectories found to clear.")
            return

    # Display preview table
    if preview:
        echo("\n⚠️  PREVIEW — No files will be deleted\n")

    if _HAS_RICH:
        from rich.table import Table

        title = "Logs Folders" if logs_only else "Output Folders"
        table = Table(title=title, border_style="yellow")
        table.add_column("Folder", style="bold")
        table.add_column("Size", justify="right")

        if logs_only:
            for lp in logs_dirs:
                parent_name = os.path.basename(os.path.dirname(lp))
                table.add_row(f"{parent_name}/logs", dir_size_str(lp))
        else:
            for d in subdirs:
                table.add_row(d, dir_size_str(os.path.join(path, d)))

        _console.print(table)
    else:
        label = "Logs folders:" if logs_only else "Output folders:"
        click.echo(label)
        if logs_only:
            for lp in logs_dirs:
                parent_name = os.path.basename(os.path.dirname(lp))
                click.echo(f"  {parent_name}/logs  ({dir_size_str(lp)})")
        else:
            for d in subdirs:
                click.echo(f"  {d}  ({dir_size_str(os.path.join(path, d))})")

    if preview:
        count = len(logs_dirs) if logs_only else len(subdirs)
        echo(f"\nWould delete {count} folder(s).")
        return

    # Confirmation
    target_count = len(logs_dirs) if logs_only else len(subdirs)
    target_label = "logs folder(s)" if logs_only else "folder(s)"
    if not force:
        if not click.confirm(f"\nDelete {target_count} {target_label}?"):
            echo("Cancelled.")
            return

    # Perform deletion
    removed = 0
    targets = logs_dirs if logs_only else [os.path.join(path, d) for d in subdirs]
    for full in targets:
        try:
            shutil.rmtree(full)
            removed += 1
        except OSError as e:
            echo_error(f"Failed to remove '{full}': {e}")

    echo(f"[bold green]✓[/bold green] Removed {removed} {target_label}." if _HAS_RICH else f"Removed {removed} {target_label}.")
