"""Thin entry point for the ``ev`` CLI.

This module exists at the top level (outside ``azure.ai.evaluation``) so that
the console-script entry point can be imported without triggering the heavy
``azure.ai.evaluation.__init__`` which eagerly loads openai, scipy, pandas, etc.

The actual CLI logic lives in ``azure.ai.evaluation._engine.cli``.
"""
import importlib.util
import os
import sys


def main():
    """Bootstrap the CLI by loading the engine CLI module directly."""
    cli_path = os.path.join(
        os.path.dirname(__file__),
        "azure", "ai", "evaluation", "_engine", "cli", "__init__.py",
    )
    spec = importlib.util.spec_from_file_location(
        "azure.ai.evaluation._engine.cli",
        cli_path,
        submodule_search_locations=[os.path.dirname(cli_path)],
    )
    cli_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cli_module
    spec.loader.exec_module(cli_module)
    cli_module.main()


if __name__ == "__main__":
    main()
