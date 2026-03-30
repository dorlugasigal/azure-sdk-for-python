# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""validate command — check configuration with optional deep validation."""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Tuple

import click

from ..utils.discovery import import_local_components
from ..utils.output import echo_error, has_rich, get_console, show_panel


def _deep_validate(cfg) -> Tuple[List[str], List[str]]:
    """Validate config by checking referenced components against registries.

    Returns:
        ``(errors, warnings)`` lists.
    """
    errors: List[str] = []
    warnings: List[str] = []

    try:
        validation_errors = cfg.deep_validate()
        errors.extend(validation_errors)
    except Exception as e:
        warnings.append(f"Deep validation failed: {e}")

    return errors, warnings


def _output_result(valid: bool, errors: List[str], warnings: List[str], output_json: bool) -> None:
    """Emit validation results as JSON or rich/plain text."""
    if output_json:
        result = {"valid": valid, "errors": errors, "warnings": warnings}
        print(json.dumps(result))
    else:
        _console = get_console()
        _HAS_RICH = has_rich()

        if valid:
            if _HAS_RICH:
                _console.print("[green]✓[/green] Config is valid")
            else:
                click.echo("✓ Config is valid")
            for w in warnings:
                if _HAS_RICH:
                    _console.print(f"  [yellow]⚠[/yellow] {w}")
                else:
                    click.echo(f"  ⚠ {w}")
        else:
            if _HAS_RICH:
                _console.print("[red]✗[/red] Config validation failed")
            else:
                click.echo("✗ Config validation failed")
            for e in errors:
                if _HAS_RICH:
                    _console.print(f"  [red]•[/red] {e}")
                else:
                    click.echo(f"  • {e}")
            for w in warnings:
                if _HAS_RICH:
                    _console.print(f"  [yellow]⚠[/yellow] {w}")
                else:
                    click.echo(f"  ⚠ {w}")

        sys.exit(0 if valid else 1)


@click.command()
@click.option("--config", "-c", default=None)
@click.option("--env", "-e", default=".env")
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON (for MCP integration)")
@click.help_option("--help", "-h")
def validate(config, env, output_json):
    """Validate configuration file.

    Performs structural validation and, when components are discoverable,
    deep validation that checks targets, evaluators, and datasets against
    their registries.
    """
    _console = get_console()
    _HAS_RICH = has_rich()

    errors: List[str] = []
    warnings: List[str] = []

    # Auto-detect config file
    if config is None:
        for candidate in ["config.yaml", "evals.yaml", "experiment/config.yaml"]:
            if os.path.exists(candidate):
                config = candidate
                break
        if config is None:
            errors.append("No config file found. Searched: config.yaml, evals.yaml, experiment/config.yaml")
            _output_result(False, errors, warnings, output_json)
            return

    if not os.path.exists(config):
        errors.append(f"Config file '{config}' not found.")
        _output_result(False, errors, warnings, output_json)
        return

    # Load .env first so config can reference env vars
    if os.path.exists(env):
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env, override=True)
        except ImportError:
            pass

    cfg = None

    try:
        from azure.ai.evaluation._engine.config import Config
        cfg = Config.from_yaml(config)

        info: Dict[str, str] = {
            "Targets": str(len(cfg.experiment.targets)),
            "Evaluators": str(len(cfg.experiment.evaluators)),
            "Dataset": cfg.experiment.dataset.name if cfg.experiment.dataset else "—",
            "Output": getattr(cfg.experiment, "output_path", "output"),
        }

        compute_cfg = getattr(cfg.experiment, "compute", None)
        if compute_cfg:
            info["Compute"] = getattr(compute_cfg, "type", "local")
        else:
            warnings.append("No compute backend configured (will use 'local' by default)")

        if not cfg.experiment.targets:
            warnings.append("No targets configured")
        if not cfg.experiment.evaluators:
            warnings.append("No evaluators configured")
        if not cfg.experiment.dataset:
            warnings.append("No dataset configured")

    except Exception as e:
        errors.append(f"Failed to parse config: {e}")

    # Deep validation — check registry membership
    if cfg is not None and len(errors) == 0:
        # Discover local components so registries are populated
        try:
            cwd = os.getcwd()
            if cwd not in sys.path:
                sys.path.insert(0, cwd)
            import_local_components(cwd)
        except Exception:
            pass

        deep_errors, deep_warnings = _deep_validate(cfg)
        errors.extend(deep_errors)
        warnings.extend(deep_warnings)

    valid = len(errors) == 0

    if output_json:
        _output_result(valid, errors, warnings, output_json)
        return

    # Rich / plain text output
    if valid and cfg is not None:
        if _HAS_RICH:
            _console.print(f"\n[bold green]✓[/bold green] Config valid: [bold]{cfg.experiment.name}[/bold]\n")
            show_panel(info, title=cfg.experiment.name)
        else:
            click.echo(f"Config valid: {cfg.experiment.name}")
            for k, v in info.items():
                click.echo(f"  {k}: {v}")

        for w in warnings:
            if _HAS_RICH:
                _console.print(f"  [yellow]⚠[/yellow] {w}")
            else:
                click.echo(f"  ⚠ {w}")
    else:
        _output_result(valid, errors, warnings, output_json)
