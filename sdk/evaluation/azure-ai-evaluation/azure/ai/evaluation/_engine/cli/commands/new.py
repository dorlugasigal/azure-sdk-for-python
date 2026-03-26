# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""new command — create evaluation project from templates."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import click

from ..utils.output import echo, echo_error, has_rich, get_console

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_UNSAFE_TOML_RE = re.compile(r'["\n\r\\]')

_SDK_GIT_REPO = "https://github.com/Azure/azure-sdk-for-python.git"


def _validate_project_name(name: str | None) -> tuple[bool, str]:
    """Return ``(is_valid, error_message)`` for a project name."""
    if not name or not name.strip():
        return False, "Project name cannot be empty."
    name = name.strip()
    if not _NAME_RE.match(name):
        return False, "Project name must contain only alphanumeric characters, hyphens, or underscores."
    if len(name) > 100:
        return False, "Project name is too long (max 100 characters)."
    return True, ""


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------


def _get_python_requires() -> str:
    """Read ``requires-python`` from azure-ai-evaluation metadata, with fallback."""
    try:
        from importlib.metadata import metadata as _pkg_metadata

        meta = _pkg_metadata("azure-ai-evaluation")
        req = meta.get("Requires-Python")
        if req:
            return req
    except Exception:
        pass

    # Fallback: try reading from this package's own pyproject.toml
    try:
        import tomllib

        pyproject = Path(__file__).resolve().parents[4] / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            return data.get("project", {}).get("requires-python", ">=3.9")
    except Exception:
        pass

    return ">=3.9"


def _resolve_dependency(
    from_source: str | None,
    from_git: bool,
) -> tuple[str, str]:
    """Return ``(ev_dependency, uv_sources_block)``."""
    if from_source:
        source_path = Path(from_source).resolve()
        uv_block = (
            "[tool.uv.sources]\n"
            f'azure-ai-evaluation = {{ path = "{source_path}", editable = true }}'
        )
        return "azure-ai-evaluation", uv_block

    if from_git:
        uv_block = (
            "[tool.uv.sources]\n"
            f'azure-ai-evaluation = {{ git = "{_SDK_GIT_REPO}", subdirectory = "sdk/evaluation/azure-ai-evaluation" }}'
        )
        return "azure-ai-evaluation", uv_block

    # Default: PyPI install — no uv sources block needed
    return "azure-ai-evaluation", ""


# ---------------------------------------------------------------------------
# Template engine
# ---------------------------------------------------------------------------


def _locate_template_dirs() -> tuple[Path, Path]:
    """Locate the base and core overlay template directories."""
    cli_dir = Path(__file__).resolve().parent.parent
    base_dir = cli_dir / "templates" / "base"
    overlay_dir = cli_dir / "templates" / "overlays" / "core"

    if not base_dir.exists() or not overlay_dir.exists():
        raise FileNotFoundError(
            f"Template directories not found. Expected:\n"
            f"  {base_dir}\n  {overlay_dir}"
        )
    return base_dir, overlay_dir


def copy_and_render_template(
    template_dirs: list[Path],
    output_dir: Path,
    replacements: dict[str, str],
) -> Path:
    """Copy template directories with layering and replace placeholders.

    Directories are copied in order — later ones overlay earlier ones using
    ``dirs_exist_ok=True``.  Every text file is scanned for ``{key}`` patterns
    from *replacements* and substituted.  Binary files are silently skipped.
    """
    if output_dir.exists():
        shutil.rmtree(output_dir)

    for i, tdir in enumerate(template_dirs):
        if not tdir.exists():
            raise FileNotFoundError(f"Template directory not found: {tdir}")
        shutil.copytree(tdir, output_dir, symlinks=False, dirs_exist_ok=(i > 0))

    # Replace placeholders in all text files
    for file_path in output_dir.rglob("*"):
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            for placeholder, value in replacements.items():
                content = content.replace(placeholder, value)
            file_path.write_text(content, encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

    return output_dir


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def _select_option(prompt: str, options: list[tuple[str, str]], default: int = 0) -> int:
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
                # Restore terminal, clean up, and abort
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
            # Move cursor up to re-render
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


def _az_run(args: list[str]) -> dict | list | None:
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


def _discover_foundry_project() -> dict[str, str] | None:
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

    # Get current subscription (don't list all — users often have 100+)
    current_sub = _az_run(["account", "show", "--query", "{name:name, id:id}", "-o", "json"])
    if not current_sub:
        echo("  Could not determine current Azure subscription.")
        return None

    echo(f"  Using subscription: [cyan]{current_sub['name']}[/cyan]" if has_rich() else f"  Using subscription: {current_sub['name']}")
    echo(f"  [dim](Change with: az account set --subscription <name>)[/dim]" if has_rich() else "  (Change with: az account set --subscription <name>)")

    # List Foundry projects in current subscription
    projects = _az_run([
        "resource", "list",
        "--resource-type", "Microsoft.CognitiveServices/accounts/projects",
        "--query", '[].{name:name, rg:resourceGroup, location:location, id:id}',
        "-o", "json",
    ])
    if not projects:
        echo("  No Foundry projects found in this subscription.")
        return None

    proj_options = [(p["name"], f'{p["rg"]} / {p["location"]}') for p in projects]
    proj_idx = _select_option("Select Foundry project:", proj_options, default=0)
    selected_proj = projects[proj_idx]

    # Parse project name — resource name is "account/project"
    full_name = selected_proj["name"]
    if "/" in full_name:
        project_name = full_name.split("/", 1)[1]
    else:
        project_name = full_name

    # Get endpoint from parent account
    parent_id = selected_proj["id"]
    # Strip /projects/<name> from the resource ID to get the parent account ID
    if "/projects/" in parent_id:
        parent_id = parent_id[: parent_id.index("/projects/")]

    endpoint_info = _az_run([
        "resource", "show",
        "--ids", parent_id,
        "--query", "{endpoint:properties.endpoint}",
        "-o", "json",
    ])

    endpoint = ""
    if endpoint_info and endpoint_info.get("endpoint"):
        endpoint = endpoint_info["endpoint"]
    else:
        echo("  Could not discover endpoint automatically.")
        endpoint = click.prompt("  Endpoint URL", type=str).strip()

    # Discover model deployments in the account
    account_name = full_name.split("/", 1)[0] if "/" in full_name else full_name
    deployments = _az_run([
        "cognitiveservices", "account", "deployment", "list",
        "--name", account_name,
        "--resource-group", selected_proj["rg"],
        "--query", "[].{name:name, model:properties.model.name, version:properties.model.version}",
        "-o", "json",
    ])

    deployment_name = ""
    if deployments:
        dep_options = [(d["name"], f'{d.get("model", "")} {d.get("version", "")}') for d in deployments]
        dep_idx = _select_option("Select model deployment:", dep_options, default=0)
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


def _run_interactive_prompts(
    description: str,
) -> tuple[str, str | None, bool, dict[str, str] | None]:
    """Run guided prompts.

    Returns ``(description, from_source, from_git, foundry_config)``.
    """
    description = click.prompt(
        "  Project description",
        default=description,
        type=str,
    )

    source_options = [
        ("pip", "Recommended — install from PyPI"),
        ("git", "Install from azure-sdk-for-python repo"),
        ("local source", "Point to a local checkout"),
    ]
    choice = _select_option("Install azure-ai-evaluation from:", source_options, default=0)

    if choice == 1:  # git
        from_source, from_git = None, True
    elif choice == 2:  # local source
        source_path = click.prompt("  Path to local azure-ai-evaluation source", type=str)
        from_source, from_git = source_path, False
    else:
        from_source, from_git = None, False

    # Foundry project selection
    foundry_config: dict[str, str] | None = None
    foundry_options = [
        ("No — local only", ""),
        ("Yes — configure Foundry project", ""),
    ]
    foundry_choice = _select_option(
        "Connect to Azure AI Foundry for remote evaluation?",
        foundry_options,
        default=0,
    )
    if foundry_choice == 1:
        foundry_config = _discover_foundry_project()

    return description, from_source, from_git, foundry_config


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command()
@click.argument("name", required=False)
@click.option("--description", "-d", default="AI model evaluation experiment", help="Project description.")
@click.option("--output", "-o", default=".", help="Output directory (default: current directory).")
@click.option(
    "--from-source",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=None,
    help="Use a local source checkout of azure-ai-evaluation (for development).",
)
@click.option("--from-git", is_flag=True, help="Install azure-ai-evaluation from the azure-sdk-for-python git repo.")
@click.option("--interactive", "-i", is_flag=True, help="Guided project setup.")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing project directory.")
@click.help_option("--help", "-h")
def new(
    name: str | None,
    description: str,
    output: str,
    from_source: str | None,
    from_git: bool,
    interactive: bool,
    force: bool,
):
    """Create a new evaluation project.

    \b
    NAME  Name of the new project (alphanumeric, hyphens, underscores).

    \b
    Source Selection:
      (default)           Install azure-ai-evaluation from PyPI
      --from-source PATH  Use a local source checkout (development)
      --from-git          Install from the azure-sdk-for-python git repository

    \b
    Examples:
      ev new my-eval-project
      ev new my-test --from-source /path/to/azure-ai-evaluation
      ev new my-test --from-git
      ev new -i
    """
    _console = get_console()
    _HAS_RICH = has_rich()

    # Mutual exclusivity
    source_flags = [
        ("--from-source", from_source is not None),
        ("--from-git", from_git),
    ]
    active = [n for n, v in source_flags if v]
    if len(active) > 1:
        echo_error(f"Source flags are mutually exclusive. Got: {', '.join(active)}")
        sys.exit(1)

    if interactive and active:
        echo_error(f"--interactive cannot be combined with source flags ({', '.join(active)}).")
        sys.exit(1)

    # Name prompt (if not provided)
    if not name:
        if interactive or sys.stdin.isatty():
            name = click.prompt("Project name", type=str)
        else:
            echo_error("Project name is required.")
            sys.exit(1)

    valid, err = _validate_project_name(name)
    if not valid:
        echo_error(err)
        sys.exit(1)
    name = name.strip()

    # Interactive mode
    if interactive:
        description, from_source, from_git, foundry_config = _run_interactive_prompts(description)
    else:
        foundry_config = None

    # Resolve dependency
    ev_dep, uv_sources_block = _resolve_dependency(from_source, from_git)

    # Locate templates
    try:
        base_dir, overlay_dir = _locate_template_dirs()
    except FileNotFoundError as exc:
        echo_error(str(exc))
        sys.exit(1)

    output_path = Path(output).resolve()
    project_path = output_path / name

    # Handle existing directory
    if project_path.exists() and not force:
        if interactive or sys.stdin.isatty():
            if not click.confirm(f"  Directory '{project_path}' already exists. Overwrite?", default=False):
                echo("  Aborted.")
                sys.exit(0)
        else:
            echo_error(f"Directory '{project_path}' already exists. Use --force to overwrite.")
            sys.exit(1)

    # Build replacements
    replacements = {
        "{project_name}": name,
        "{description}": description,
        "{python_requires}": _get_python_requires(),
        "{ev_dependency}": ev_dep,
        "{uv_sources_block}": uv_sources_block,
    }

    try:
        copy_and_render_template(
            template_dirs=[base_dir, overlay_dir],
            output_dir=project_path,
            replacements=replacements,
        )
    except Exception as exc:
        echo_error(f"Failed to create project: {exc}")
        sys.exit(1)

    # ---- Foundry configuration injection ----
    if foundry_config:
        # Write .env with Foundry variables
        env_path = project_path / ".env"
        env_lines = [
            "# Evaluation configuration",
            "LOG_LEVEL=INFO",
            "",
            "# Azure OpenAI connection",
            f"AZURE_OPENAI_ENDPOINT={foundry_config['endpoint']}",
            "",
            "# Azure AI Foundry",
            f"AZURE_SUBSCRIPTION_ID={foundry_config['subscription_id']}",
            f"AZURE_RESOURCE_GROUP={foundry_config['resource_group']}",
            f"AZURE_AI_PROJECT_NAME={foundry_config['project_name']}",
            f"AZURE_AI_PROJECT_ENDPOINT={foundry_config['endpoint']}",
            "",
        ]
        env_path.write_text("\n".join(env_lines), encoding="utf-8")

        # Inject compute_backend into config.yaml
        config_path = project_path / "config.yaml"
        if config_path.exists():
            config_text = config_path.read_text(encoding="utf-8")
            foundry_sections = (
                '\n  compute_backend:\n'
                '    type: "foundry"\n'
                '    azure_ai_project: "${AZURE_AI_PROJECT_ENDPOINT}"\n'
            )
            # Insert before the connections section
            if "  connections:" in config_text:
                config_text = config_text.replace(
                    "  connections:",
                    foundry_sections + "\n  connections:",
                )
            else:
                config_text += foundry_sections

            # Update default connection endpoint to Foundry endpoint
            config_text = config_text.replace(
                'endpoint: "${AZURE_OPENAI_ENDPOINT}"',
                'endpoint: "${AZURE_AI_PROJECT_ENDPOINT}"',
            )

            # Update deployment to discovered one (if any)
            discovered_deployment = foundry_config.get("deployment", "")
            if discovered_deployment:
                config_text = config_text.replace(
                    'deployment: "gpt-4"',
                    f'deployment: "{discovered_deployment}"',
                )

            config_path.write_text(config_text, encoding="utf-8")

    # ---- Success output ----
    if _HAS_RICH:
        _console.print(f"\n[bold green]✓[/bold green] Project [bold]{name}[/bold] created successfully!")
        _console.print(f"[dim]Location:[/dim] {project_path}\n")
        _console.print("  [cyan]pyproject.toml[/cyan]                    — project & dependencies")
        _console.print("  [cyan]config.yaml[/cyan]                      — experiment configuration")
        _console.print("  [cyan]data/sample_dataset.jsonl[/cyan]         — sample dataset (3 records)")
        _console.print("  [cyan]evaluators/word_count.py[/cyan]          — custom @evaluator example")
        _console.print("  [cyan]targets/baseline.py[/cyan]               — sample @target")
        if foundry_config:
            _console.print("  [cyan].env[/cyan]                             — Foundry credentials (pre-configured)")

        _console.print(f"\n[bold]Next steps:[/bold]")
        _console.print(f"  1. cd {project_path}")
        if foundry_config:
            _console.print("  2. uv sync")
            _console.print("  3. ev run")
            _console.print("  4. ev run --remote  # run on Foundry\n")
        else:
            _console.print("  2. cp .env.sample .env  # add your credentials")
            _console.print("  3. uv sync")
            _console.print("  4. ev run\n")
    else:
        click.echo(f"\nCreated evaluation project: {name}/")
        click.echo(f"  Location: {project_path}\n")
        click.echo("  pyproject.toml                    — project & dependencies")
        click.echo("  config.yaml                      — experiment configuration")
        click.echo("  data/sample_dataset.jsonl         — sample dataset (3 records)")
        click.echo("  evaluators/word_count.py          — custom @evaluator example")
        click.echo("  targets/baseline.py               — sample @target")
        if foundry_config:
            click.echo("  .env                             — Foundry credentials (pre-configured)")
        click.echo(f"\nNext steps:")
        click.echo(f"  1. cd {project_path}")
        if foundry_config:
            click.echo("  2. uv sync")
            click.echo("  3. ev run")
            click.echo("  4. ev run --remote  # run on Foundry")
        else:
            click.echo("  2. cp .env.sample .env  # add your credentials")
            click.echo("  3. uv sync")
            click.echo("  4. ev run")
