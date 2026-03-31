# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""CLI for azure-ai-evaluation v2.0 — ev command (modular structure).

This package provides the ``ev`` CLI entry point.  The click group
and all sub-commands are assembled here so that a single ``from
azure.ai.evaluation._engine.cli import main`` gives callers the full CLI.

Environment delegation
----------------------
When installed globally (or in a different venv than the project), the CLI
automatically detects the project's Python environment and re-executes the
command there.  This is controlled by ``_should_delegate_to_project_env()``
and ``_execute_in_project_env()``.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import click

from .commands.clear import clear
from .commands.cloud import cloud
from .commands.compute import compute
from .commands.connection import connection
from .commands.dataset import dataset
from .commands.list_cmd import discover
from .commands.evaluator_cmd import evaluator
from .commands.new import new
from .commands.run import run
from .commands.target import target_cmd
from .commands.validate import validate
from .commands.view import view
from .utils.constants import EV_ASCII
from .utils.output import has_rich, get_console, echo_error

# Default file names used when extracting project info from CLI args
_DEFAULT_CONFIG_FILE = "config.yaml"
_DEFAULT_ENV_FILE = ".env"

# Commands that should NOT be delegated to the project environment.
# These operate on the file system directly and don't need project-specific packages.
_NON_DELEGATED_COMMANDS = frozenset({"new", "dataset", "evaluator", "clear", "view", "connection", "cloud"})

# CLI flags that accept file / directory path arguments
_PATH_FLAGS = frozenset({
    "--path", "-p",
    "--config", "-c",
    "--dataset", "-d",
    "--env", "-e",
    "--output", "-o",
})


def _set_plain_output(_ctx, _param, value):
    """Eager callback to disable Rich formatting before subcommands run."""
    if value:
        os.environ["EV_DISABLE_RICH_LOGGING"] = "true"


class OrderedGroup(click.Group):
    """Maintains command insertion order."""

    def list_commands(self, _ctx):
        return list(self.commands.keys())


@click.group(invoke_without_command=True, cls=OrderedGroup)
@click.version_option(version="2.0.0a1", prog_name="ev")
@click.option(
    "--plain",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_set_plain_output,
    help="Disable ASCII art and Rich formatting. Uses plain log output.",
)
@click.pass_context
def cli(ctx):
    """Azure AI Evaluation — local-first evaluation toolkit."""
    if ctx.invoked_subcommand is None:
        if has_rich():
            get_console().print(EV_ASCII, highlight=False)
        click.echo(ctx.get_help())


# Register all commands in desired display order
cli.add_command(run)
cli.add_command(new)
cli.add_command(validate)
cli.add_command(discover)
cli.add_command(view)
cli.add_command(clear)
cli.add_command(cloud)
cli.add_command(compute)
cli.add_command(target_cmd, name="target")
cli.add_command(evaluator)
cli.add_command(dataset)
cli.add_command(connection)


# ---------------------------------------------------------------------------
# Environment delegation helpers
# ---------------------------------------------------------------------------


def _should_delegate_to_project_env() -> bool:
    """Return True if the CLI should re-execute inside the project's venv.

    Delegation is skipped for:
    * ``--version`` / ``-v`` and ``--help`` / ``-h`` (fast, always work)
    * Commands that don't need project context (see ``_NON_DELEGATED_COMMANDS``)
    * Bare invocation with no arguments
    """
    if len(sys.argv) <= 1:
        return False

    args = sys.argv[1:]

    # Never delegate for help / version — they must work even when the
    # project environment is broken.
    if any(a in ("--version", "-v", "--help", "-h") for a in args):
        return False

    # Find the first positional (non-flag) argument — that is the subcommand.
    for arg in args:
        if not arg.startswith("-"):
            return arg not in _NON_DELEGATED_COMMANDS

    # Only flags, no subcommand → don't delegate
    return False


def _extract_project_info_from_args() -> Tuple[str, Optional[str], bool, Optional[str]]:
    """Parse CLI args to determine project path, config path, and env path.

    Returns:
        ``(project_path, config_path, config_explicit, env_path)``
    """
    args = sys.argv[1:]
    project_path = os.getcwd()
    config_path: Optional[str] = None
    config_explicit = False
    env_path: Optional[str] = None

    # Extract --path / -p
    for i, arg in enumerate(args):
        if arg in ("-p", "--path") and i + 1 < len(args):
            p = args[i + 1]
            if os.path.isdir(p):
                project_path = os.path.abspath(p)
            else:
                echo_error(f"Path '{p}' does not exist or is not a directory")
                sys.exit(1)
            break

    # Extract --config / -c
    for i, arg in enumerate(args):
        if arg in ("--config", "-c") and i + 1 < len(args):
            cfg = args[i + 1]
            config_explicit = True
            if os.path.isabs(cfg):
                config_path = cfg
            elif cfg.startswith("./") or cfg.startswith("../"):
                config_path = os.path.abspath(cfg)
            else:
                config_path = os.path.abspath(os.path.join(project_path, cfg))
            break

    if config_path is None:
        default_config = os.path.join(project_path, _DEFAULT_CONFIG_FILE)
        if os.path.isfile(default_config):
            config_path = default_config

    # Extract --env / -e
    for i, arg in enumerate(args):
        if arg in ("--env", "-e") and i + 1 < len(args):
            env = args[i + 1]
            if os.path.isabs(env):
                env_path = env
            elif env.startswith("./") or env.startswith("../"):
                env_path = os.path.abspath(env)
            else:
                env_path = os.path.abspath(os.path.join(project_path, env))
            break

    if env_path is None:
        default_env = os.path.join(project_path, _DEFAULT_ENV_FILE)
        if os.path.isfile(default_env):
            env_path = default_env

    return project_path, config_path, config_explicit, env_path


def _normalize_cli_args_for_delegation(args: List[str]) -> List[str]:
    """Convert relative path arguments to absolute so they survive a cwd change.

    Handles separated flag syntax (``--config file.yaml``) but not combined
    short flags or ``=`` syntax.  Users should use separated flags for reliable
    path normalisation.
    """
    # First pass — find the project path if specified
    project_path: Optional[str] = None
    for i, arg in enumerate(args):
        if arg in ("--path", "-p") and i + 1 < len(args):
            p = args[i + 1]
            project_path = os.path.abspath(p) if not os.path.isabs(p) else p
            break

    # Second pass — normalise every path-valued argument
    normalised: List[str] = []
    for i, arg in enumerate(args):
        if i > 0 and args[i - 1] in _PATH_FLAGS:
            if args[i - 1] in ("--path", "-p"):
                # --path is always relative to cwd
                normalised.append(os.path.abspath(arg) if not os.path.isabs(arg) else arg)
            elif not os.path.isabs(arg):
                if arg.startswith("./") or arg.startswith("../"):
                    normalised.append(os.path.abspath(arg))
                else:
                    base = project_path if project_path else os.getcwd()
                    normalised.append(os.path.abspath(os.path.join(base, arg)))
            else:
                normalised.append(arg)
        else:
            normalised.append(arg)

    return normalised


def _execute_in_project_env() -> None:
    """Detect the project venv and re-execute the current command there.

    Avoids importing from ``azure.ai.evaluation._engine`` (which triggers
    the heavy parent ``__init__``) by loading the environment module directly.
    """
    _console = get_console()

    project_path, config_path, config_explicit, env_path = (
        _extract_project_info_from_args()
    )

    # Load .env before environment detection so config can reference env vars
    if env_path and os.path.isfile(env_path):
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_path, override=True)
        except ImportError:
            pass

    cli_args = _normalize_cli_args_for_delegation(sys.argv[1:])

    try:
        # Load environment module directly to avoid triggering
        # azure.ai.evaluation.__init__ (openai, scipy, pandas, etc.)
        env_module_path = Path(__file__).parent.parent / "environment.py"
        spec = importlib.util.spec_from_file_location(
            "azure.ai.evaluation._engine.environment",
            str(env_module_path),
        )
        env_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = env_module
        spec.loader.exec_module(env_module)

        EnvironmentResolver = env_module.EnvironmentResolver
        ProjectEnvironmentError = env_module.ProjectEnvironmentError

        resolver = EnvironmentResolver()

        # Only detect the Python executable — skip the slow version/package
        # checks (get_environment_info spawns subprocesses).
        python_exe = resolver.detect_python(
            project_path,
            config_path=config_path,
            config_explicit=config_explicit,
        )
        env_type = resolver._determine_env_type(project_path, python_exe)

        # Fast check: does the target venv have the package installed?
        python_path = Path(python_exe)
        venv_dir = python_path.parent.parent
        has_package = (
            any(p.is_dir() for p in venv_dir.glob("lib/python*/site-packages/azure/ai/evaluation"))
            or any(venv_dir.glob("lib/python*/site-packages/__editable__.azure_ai_evaluation*"))
            or any(venv_dir.glob("lib/python*/site-packages/azure_ai_evaluation*"))
            or (venv_dir / "bin" / "ev").exists()
        )
        if not has_package:
            return  # package not installed in project venv — run locally

        if has_rich() and _console is not None:
            _console.print(
                f"[dim]Using Python environment: "
                f"[cyan]{env_type}[/cyan] ({python_exe})[/dim]"
            )
        else:
            click.echo(f"Using Python environment: {env_type} ({python_exe})")

        # Hint about first-run slowness. We drop a tiny marker file after the
        # first successful delegation so we only show this once.
        cache_marker = venv_dir / ".ev_first_run"
        if not cache_marker.exists():
            if has_rich() and _console is not None:
                _console.print("[dim]First run may take a moment while dependencies are loaded...[/dim]")
            else:
                click.echo("First run may take a moment while dependencies are loaded...")
            try:
                cache_marker.touch()
            except OSError:
                pass

        # Use the venv's `ev` console script (fast) or fall back to -m
        bootstrap = python_path.parent / "ev"
        if bootstrap.exists():
            cmd = [str(bootstrap)] + cli_args
        else:
            ev_cli_candidates = list(venv_dir.glob("lib/python*/site-packages/ev_cli.py"))
            if ev_cli_candidates:
                cmd = [python_exe, str(ev_cli_candidates[0])] + cli_args
            else:
                cmd = [python_exe, "-m", "azure.ai.evaluation._engine.cli"] + cli_args

        env = os.environ.copy()
        env["EV_EXECUTION_MODE"] = "direct"  # prevent infinite recursion

        result = subprocess.run(cmd, env=env)
        sys.exit(result.returncode)

    except Exception as e:
        if "ProjectEnvironmentError" in type(e).__name__:
            echo_error(f"Environment Error: {e}")
            click.echo(
                "Tip: Use -p/--path to specify the project directory, "
                "configure runtime.python_executable in your config, "
                "or ensure azure-ai-evaluation is installed in your project venv.",
                err=True,
            )
            sys.exit(1)
        # For any other error (import failure, etc.), fall through to local CLI
        return


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Entry point for the ``ev`` CLI.

    Handles transparent environment delegation: if running from a global
    install, automatically detects the project's Python environment and
    re-executes the command there.
    """
    # Early --plain detection (before Click parses args) so delegation output
    # respects the flag.
    if "--plain" in sys.argv:
        os.environ["EV_DISABLE_RICH_LOGGING"] = "true"

    execution_mode = os.environ.get("EV_EXECUTION_MODE")

    if execution_mode == "direct":
        # Already in the project environment — execute normally
        cli()
    elif _should_delegate_to_project_env():
        # Returns without calling sys.exit when the project venv
        # doesn't have the package — fall through to cli() in that case.
        _execute_in_project_env()
        cli()
    else:
        # Help, version, non-delegated commands, or bare invocation
        cli()


__all__ = ["main"]
