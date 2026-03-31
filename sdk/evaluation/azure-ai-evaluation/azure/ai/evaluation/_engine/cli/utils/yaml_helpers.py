# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Shared YAML loading and writing utilities."""
from __future__ import annotations

import yaml


def _ensure_quoted_strings(data):
    """Wrap plain string values in DoubleQuotedScalarString so ruamel preserves quotes."""
    try:
        from ruamel.yaml.scalarstring import DoubleQuotedScalarString
    except ImportError:
        return

    if isinstance(data, dict):
        for key in list(data.keys()):
            val = data[key]
            if isinstance(val, str) and not isinstance(val, DoubleQuotedScalarString):
                data[key] = DoubleQuotedScalarString(val)
            elif isinstance(val, (dict, list)):
                _ensure_quoted_strings(val)
    elif isinstance(data, list):
        for i, val in enumerate(data):
            if isinstance(val, str) and not isinstance(val, DoubleQuotedScalarString):
                data[i] = DoubleQuotedScalarString(val)
            elif isinstance(val, (dict, list)):
                _ensure_quoted_strings(val)


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
        _ensure_quoted_strings(data)
        with open(path, "w", encoding="utf-8") as f:
            ry.dump(data, f)
    except ImportError:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
