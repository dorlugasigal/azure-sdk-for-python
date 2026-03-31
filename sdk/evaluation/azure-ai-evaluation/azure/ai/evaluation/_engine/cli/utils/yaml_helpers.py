# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Shared YAML loading and writing utilities."""
from __future__ import annotations

import yaml


def load_yaml_raw(path: str) -> dict:
    """Load YAML file using PyYAML (safe_load)."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_yaml_ruamel(path: str):
    """Load YAML file using ruamel.yaml (preserves comments/formatting).

    Falls back to PyYAML if ruamel is not installed.
    """
    try:
        from ruamel.yaml import YAML

        ry = YAML()
        with open(path, encoding="utf-8") as f:
            return ry.load(f)
    except ImportError:
        return load_yaml_raw(path)


def write_yaml_ruamel(path: str, data) -> None:
    """Write YAML file using ruamel.yaml (preserves comments/formatting).

    Falls back to PyYAML if ruamel is not installed.
    """
    try:
        from ruamel.yaml import YAML

        ry = YAML()
        ry.preserve_quotes = True  # type: ignore[assignment]
        with open(path, "w", encoding="utf-8") as f:
            ry.dump(data, f)
    except ImportError:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
