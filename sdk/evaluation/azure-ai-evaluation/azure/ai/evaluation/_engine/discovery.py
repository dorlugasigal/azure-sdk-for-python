"""Auto-discovery of decorated components using AST."""
from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Set

# Cache for tracking discovered modules
_DISCOVERED_DIRECTORIES: Set[Path] = set()
_IMPORTED_MODULES: Set[str] = set()


def discover_components(force: bool = False) -> None:
    """Discover and import all @metric, @model, @dataset decorated components.

    Scans the current working directory for Python modules containing these
    decorators and imports them to populate the registries.

    Args:
        force: If True, forces discovery even if directory was already scanned.
    """
    base_dir = Path.cwd()

    if not force and base_dir in _DISCOVERED_DIRECTORIES:
        return

    from .decorators import DATASET_REGISTRY, METRIC_REGISTRY, TARGET_REGISTRY

    initial_models = len(TARGET_REGISTRY)
    initial_metrics = len(METRIC_REGISTRY)
    initial_datasets = len(DATASET_REGISTRY)

    _discover_in_directory(base_dir)
    _DISCOVERED_DIRECTORIES.add(base_dir)

    # Could add logging here if needed
    models_found = len(TARGET_REGISTRY) - initial_models
    metrics_found = len(METRIC_REGISTRY) - initial_metrics
    datasets_found = len(DATASET_REGISTRY) - initial_datasets


def _contains_decorator_syntax(content: str, target_decorators: Set[str]) -> bool:
    """Fast text-based check for decorator syntax."""
    return any(f"@{name}" in content for name in target_decorators)


def _has_decorator_on_class(tree: ast.AST, target_decorators: Set[str]) -> bool:
    """Check if target decorators are applied to class definitions."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for decorator in node.decorator_list:
                decorator_name = None
                if isinstance(decorator, ast.Name):
                    decorator_name = decorator.id
                elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                    decorator_name = decorator.func.id

                if decorator_name in target_decorators:
                    return True
    return False


def _discover_in_directory(directory: Path) -> None:
    """Recursively discover Python modules with evee decorators."""
    exclude_dirs = {
        ".venv",
        "venv",
        "env",
        ".env",
        "__pycache__",
        ".pytest_cache",
        ".git",
        "node_modules",
        ".tox",
        ".mypy_cache",
        "build",
        "dist",
        ".eggs",
        "output",
        "logs",
        "samples",
        "tests",
        "experiment",
    }

    target_decorators = {"model", "metric", "dataset", "target", "evaluator"}
    exclude_dirs_frozen = frozenset(exclude_dirs)

    def _is_excluded_path(path: Path) -> bool:
        return any(excluded in path.parts for excluded in exclude_dirs_frozen)

    try:
        import os

        python_files = []
        for root, dirs, files in os.walk(directory):
            root_path = Path(root)

            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs_frozen]

            # Collect Python files (excluding private modules)
            for file in files:
                if file.endswith(".py") and not file.startswith("_"):
                    file_path = root_path / file
                    if not _is_excluded_path(file_path):
                        python_files.append(file_path)

        # Process files
        for file_path in python_files:
            try:
                relative_path = file_path.relative_to(Path.cwd())
                module_path = ".".join(relative_path.with_suffix("").parts)
            except ValueError:
                continue

            # Skip if already imported
            if module_path in _IMPORTED_MODULES:
                continue

            # Two-phase decorator detection
            try:
                content = file_path.read_text(encoding="utf-8")

                # Phase 1: Fast text search
                if not _contains_decorator_syntax(content, target_decorators):
                    continue

                # Phase 2: Parse and validate
                try:
                    tree = ast.parse(content, filename=str(file_path))
                except SyntaxError:
                    continue

                if not _has_decorator_on_class(tree, target_decorators):
                    continue

            except Exception:
                continue

            # Import the module
            try:
                import importlib.util as _ilu
                spec = _ilu.spec_from_file_location(module_path, str(file_path))
                if spec and spec.loader:
                    import sys
                    mod = _ilu.module_from_spec(spec)
                    sys.modules[module_path] = mod
                    spec.loader.exec_module(mod)
                    _IMPORTED_MODULES.add(module_path)
            except Exception:
                # Continue with other modules even if one fails
                pass

    except Exception:
        pass
