"""CLI entry point — delegates to modular CLI structure.

The ``ev`` console-script entry point (defined in setup.py as
``azure.ai.evaluation.cli:main``) is redirected here to the new modular
CLI package.  The previous monolithic implementation that lived in this
file has been replaced by ``azure.ai.evaluation._engine.cli``.
"""
import importlib.util
import os
import sys


def main():
    """Entry point for the ``ev`` CLI — loads directly to avoid slow startup.

    The parent ``azure.ai.evaluation.__init__`` eagerly imports heavy
    dependencies (openai, scipy, pandas).  We bypass that by loading
    the CLI module directly from its file path.
    """
    cli_path = os.path.join(os.path.dirname(__file__), "_engine", "cli", "__init__.py")
    spec = importlib.util.spec_from_file_location(
        "azure.ai.evaluation._engine.cli",
        cli_path,
        submodule_search_locations=[os.path.dirname(cli_path)],
    )
    cli_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cli_module
    spec.loader.exec_module(cli_module)
    cli_module.main()


__all__ = ["main"]

if __name__ == "__main__":
    main()
