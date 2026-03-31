# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""dataset command group — manage evaluation datasets."""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from ..utils.constants import resolve_config_path
from ..utils.discovery import import_local_components, discover_project_components
from ..utils.output import echo, echo_error, has_rich
from ..utils.yaml_helpers import load_yaml_raw, load_yaml_ruamel, write_yaml_ruamel


DEFAULT_CONFIG = "config.yaml"

SUPPORTED_TYPES = ("jsonl", "csv")

SAMPLE_JSONL = """\
{"question": "What is the capital of France?", "answer": "Paris", "context": "France is a country in Europe."}
{"question": "What is the speed of light?", "answer": "299792458 m/s", "context": "Light travels at approximately 3×10^8 meters per second in vacuum."}
{"question": "Who wrote Hamlet?", "answer": "William Shakespeare", "context": "Hamlet is a tragedy written by William Shakespeare around 1600."}
"""

SAMPLE_CSV = """\
question,answer,context
"What is the capital of France?","Paris","France is a country in Europe."
"What is the speed of light?","299792458 m/s","Light travels at approximately 3×10^8 meters per second in vacuum."
"Who wrote Hamlet?","William Shakespeare","Hamlet is a tragedy written by William Shakespeare around 1600."
"""


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def read_dataset_from_config(config_path: Path) -> Optional[Dict[str, Any]]:
    """Read dataset configuration from YAML."""
    try:
        data = load_yaml_raw(str(config_path))
    except Exception:
        return None

    if not data or "experiment" not in data:
        return None

    return data["experiment"].get("dataset")


def update_dataset_in_config(
    config_path: Path, name: str, dataset_type: str, data_path: str,
) -> bool:
    """Update dataset entry in config YAML."""
    try:
        data = load_yaml_ruamel(str(config_path))
        if data is None:
            data = {}

        experiment = data.setdefault("experiment", {})
        experiment["dataset"] = {
            "name": name,
            "type": dataset_type,
            "version": "1.0.0",
            "args": {"data_path": data_path},
        }

        write_yaml_ruamel(str(config_path), data)
        return True
    except Exception:
        return False


def _get_file_size_str(path: Path) -> str:
    """Return human-readable file size."""
    size = float(path.stat().st_size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _get_first_record(path: Path, dataset_type: str) -> Optional[Dict[str, Any]]:
    """Read the first record from a dataset file."""
    try:
        if dataset_type == "jsonl":
            with open(path, encoding="utf-8") as f:
                line = f.readline().strip()
                return json.loads(line) if line else None
        elif dataset_type == "csv":
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                return dict(next(reader))
    except Exception:
        return None
    return None


def _infer_dataset_type(path: Path) -> str:
    """Infer dataset type from file extension."""
    ext = path.suffix.lower().lstrip(".")
    if ext in ("jsonl",):
        return "jsonl"
    if ext in ("csv",):
        return "csv"
    raise ValueError(f"Unsupported file type: {path.suffix}")


# ---------------------------------------------------------------------------
# Click commands
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.pass_context
def dataset(ctx):
    """Manage evaluation datasets — add or show dataset information."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@dataset.command()
@click.option("--type", "-t", "dataset_type", type=click.Choice(SUPPORTED_TYPES), help="Dataset format (csv or jsonl) — for creating a sample.")
@click.option("--from", "-f", "from_file", type=click.Path(exists=True), help="Path to existing dataset file — for importing.")
@click.option("--name", "-n", required=True, help="Dataset name (as it appears in config).")
@click.option("--output", "-o", type=click.Path(), default="data", help="Output directory (default: data).")
@click.option("--config", "-c", type=click.Path(), default=None, help="Path to config file (default: config.yaml).")
@click.option("--force", "-F", is_flag=True, help="Overwrite existing file and config without prompting.")
@click.help_option("--help", "-h")
def add(dataset_type, from_file, name, output, config, force):
    """Add a dataset to the project — create a sample or import a file.

    Examples:\n
      ev dataset add --type jsonl --name eval_data\n
      ev dataset add --from ~/data.csv --name eval_data\n
      ev dataset add --from data.jsonl --name my_data --force
    """
    if dataset_type and from_file:
        echo_error("Cannot specify both --type and --from.")
        echo("  Use --type to create a sample OR --from to import a file.")
        sys.exit(1)

    if not dataset_type and not from_file:
        echo_error("Must specify either --type or --from.")
        echo("  • --type to create a minimal sample dataset")
        echo("  • --from to import your existing dataset")
        sys.exit(1)

    output_dir = Path(output)
    config = resolve_config_path(config)
    config_path = Path(config)

    if dataset_type:
        _create_sample_dataset(dataset_type, name, output_dir, config_path, force)
    elif from_file:
        _import_dataset(Path(from_file), name, output_dir, config_path, force)


def _create_sample_dataset(
    dataset_type: str, name: str, output_dir: Path, config_path: Path, force: bool,
):
    """Create a minimal sample dataset."""
    _HAS_RICH = has_rich()
    output_file = output_dir / f"sample_dataset.{dataset_type}"

    if output_file.exists() and not force:
        echo_error(f"Dataset file already exists: {output_file}. Use --force to overwrite.")
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    content = SAMPLE_JSONL if dataset_type == "jsonl" else SAMPLE_CSV
    output_file.write_text(content, encoding="utf-8")

    echo(
        f"[bold green]✅[/bold green] Created dataset: {output_file}"
        if _HAS_RICH
        else f"✅ Created dataset: {output_file}"
    )

    if config_path.exists():
        if update_dataset_in_config(config_path, name, dataset_type, str(output_file)):
            echo(
                f"[bold green]✅[/bold green] Updated {config_path}"
                if _HAS_RICH
                else f"✅ Updated {config_path}"
            )
            echo("\n⚠️  This is placeholder data for testing only!")
            echo("   Replace it with your own data for real evaluations.")
        else:
            echo_error(f"Could not update {config_path}")

    echo("\nNext step: ev run")


def _import_dataset(
    source_file: Path, name: str, output_dir: Path, config_path: Path, force: bool,
):
    """Import an existing dataset file."""
    _HAS_RICH = has_rich()

    try:
        dataset_type = _infer_dataset_type(source_file)
    except ValueError:
        echo_error(f"Unsupported file type: {source_file.suffix}")
        echo(f"\nSupported types: {', '.join(SUPPORTED_TYPES)}")
        sys.exit(1)

    output_file = output_dir / source_file.name

    if output_file.exists() and not force:
        echo_error(f"Dataset file already exists: {output_file}. Use --force to overwrite.")
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source_file), str(output_file))

    echo(
        f"[bold green]✅[/bold green] Imported dataset: {output_file}"
        if _HAS_RICH
        else f"✅ Imported dataset: {output_file}"
    )

    if config_path.exists():
        if update_dataset_in_config(config_path, name, dataset_type, str(output_file)):
            echo(
                f"[bold green]✅[/bold green] Updated {config_path}"
                if _HAS_RICH
                else f"✅ Updated {config_path}"
            )
        else:
            echo_error(f"Could not update {config_path}")

    echo("\nReady to run: ev run")


@dataset.command()
@click.option("--config", "-c", type=click.Path(), default=None, help="Path to config (default: config.yaml).")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information with sample records.")
@click.help_option("--help", "-h")
def show(config, verbose):
    """Show information about the configured dataset.

    Examples:\n
      ev dataset show\n
      ev dataset show --verbose
    """
    _HAS_RICH = has_rich()
    config = resolve_config_path(config)
    config_path = Path(config)

    if not config_path.exists():
        echo_error(f"Config file not found: {config_path}")
        sys.exit(1)

    dataset_config = read_dataset_from_config(config_path)

    if not dataset_config:
        echo("No dataset configured.")
        echo("\nCreate a dataset with:")
        echo("  ev dataset add --type jsonl --name my_dataset")
        echo("  ev dataset add --from <file> --name my_dataset")
        return

    ds_name = dataset_config.get("name", "Unknown")
    dataset_type = dataset_config.get("type", "Unknown")
    version = dataset_config.get("version", "Unknown")
    data_path = dataset_config.get("args", {}).get("data_path", "Unknown")

    echo(
        f"\n[bold]Dataset (from {config_path}):[/bold]\n"
        if _HAS_RICH
        else f"\nDataset (from {config_path}):\n"
    )
    echo(f"  Name:    {ds_name}")
    echo(f"  Type:    {dataset_type}")
    echo(f"  Version: {version}")
    echo(f"  Path:    {data_path}")

    dataset_file = Path(data_path)
    if not dataset_file.exists():
        echo_error(f"\n  File not found: {data_path}")
        return

    echo(f"\n  Size: {_get_file_size_str(dataset_file)}")

    first = _get_first_record(dataset_file, dataset_type)
    if first:
        echo(f"\n  First record: {json.dumps(first, ensure_ascii=False)[:200]}")

    if verbose and first:
        echo(f"\n  Fields: {', '.join(first.keys())}")
        echo("\n  Sample records:")
        try:
            if dataset_type == "jsonl":
                with open(dataset_file, encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if i > 3:
                            break
                        record = json.loads(line.strip())
                        echo(f"    {i}. {json.dumps(record, ensure_ascii=False)[:200]}")
            elif dataset_type == "csv":
                with open(dataset_file, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for i, row in enumerate(reader, 1):
                        if i > 3:
                            break
                        echo(f"    {i}. {json.dumps(dict(row), ensure_ascii=False)[:200]}")
        except Exception as e:
            echo(f"  Could not display sample records: {e}")
