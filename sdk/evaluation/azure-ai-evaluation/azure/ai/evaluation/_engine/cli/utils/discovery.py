# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Component discovery helpers for the CLI."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import sys
from typing import Dict, List

from .constants import BUILTIN_EVALUATORS


def import_local_components(directory: str) -> None:
    """Import Python files in directory (and subdirs) that contain @target, @evaluator, or @dataset decorators."""
    decorator_names = ("target", "evaluator", "dataset")

    for root, dirs, files in os.walk(directory):
        # Skip hidden dirs, __pycache__, node_modules, .venv
        dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d not in ("node_modules", "venv")]
        for fname in files:
            if not fname.endswith(".py") or fname.startswith("_") or fname.startswith("demo_"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath) as f:
                    content = f.read()
                if any(f"@{d}" in content for d in decorator_names):
                    tree = ast.parse(content)
                    has_decorator = any(
                        isinstance(node, ast.ClassDef)
                        and any(
                            (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id in decorator_names)
                            or (isinstance(d, ast.Name) and d.id in decorator_names)
                            for d in node.decorator_list
                        )
                        for node in ast.walk(tree)
                    )
                    if has_decorator:
                        # Build module name relative to directory
                        rel_path = os.path.relpath(fpath, directory)
                        module_name = rel_path[:-3].replace(os.sep, ".")
                        if module_name not in sys.modules:
                            spec = importlib.util.spec_from_file_location(module_name, fpath)
                            if spec and spec.loader:
                                mod = importlib.util.module_from_spec(spec)
                                sys.modules[module_name] = mod
                                spec.loader.exec_module(mod)
            except Exception:
                pass


def discover_project_components() -> Dict[str, List[str]]:
    """Discover @target, @evaluator, @dataset components from registries.

    Returns dict with keys 'targets', 'evaluators' (custom only), 'datasets'.
    SDK bridge evaluators are excluded — use BUILTIN_EVALUATOR_NAMES for those.
    """
    found: Dict[str, List[str]] = {"targets": [], "evaluators": [], "datasets": []}
    try:
        from azure.ai.evaluation._engine.decorators import (
            TARGET_REGISTRY,
            EVALUATOR_REGISTRY,
            DATASET_REGISTRY,
        )
        from azure.ai.evaluation._engine.dataset_factory import _ensure_builtin_datasets

        _ensure_builtin_datasets()

        found["targets"] = sorted(TARGET_REGISTRY.keys())
        # Filter out SDK bridge evaluators — only show truly custom ones
        builtin_names = {name for name, _, _ in BUILTIN_EVALUATORS}
        found["evaluators"] = sorted(
            name for name in EVALUATOR_REGISTRY if name not in builtin_names
        )
        # Filter out built-in dataset types — only show custom ones
        builtin_datasets = {"csv", "jsonl"}
        found["datasets"] = sorted(
            name for name in DATASET_REGISTRY if name not in builtin_datasets
        )
    except ImportError:
        pass
    return found


def load_config_safe(config_path: str):
    """Load Config from YAML, returning None on failure."""
    try:
        from azure.ai.evaluation._engine.models.config import Config
        return Config.from_yaml(config_path)
    except Exception:
        return None


def dir_size_str(path: str) -> str:
    """Return human-readable size of a directory tree."""
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024:
            return f"{total:.1f} {unit}"
        total /= 1024
    return f"{total:.1f} TB"
