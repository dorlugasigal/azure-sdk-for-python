# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Allow ``python -m azure.ai.evaluation._engine.cli`` invocation.

Uses direct file loading to avoid triggering the heavy
``azure.ai.evaluation.__init__`` import chain.
"""
import importlib.util
import os
import sys


def _bootstrap():
    cli_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__init__.py")
    spec = importlib.util.spec_from_file_location(
        "azure.ai.evaluation._engine.cli",
        cli_path,
        submodule_search_locations=[os.path.dirname(cli_path)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    mod.main()


_bootstrap()
