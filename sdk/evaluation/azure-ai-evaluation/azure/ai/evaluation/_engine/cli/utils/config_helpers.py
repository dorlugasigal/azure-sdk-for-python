# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Shared config section read/write helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .yaml_helpers import load_yaml_raw, load_yaml_ruamel, write_yaml_ruamel


def read_config_section(config_path: Path, section_name: str) -> List[Dict[str, Any]]:
    """Read a list section (targets/evaluators/datasets) from experiment config YAML."""
    try:
        data = load_yaml_raw(str(config_path))
    except Exception:
        return []

    if not data or "experiment" not in data:
        return []

    experiment = data["experiment"]
    items = experiment.get(section_name, [])
    return items if items else []


def add_to_config_section(config_path: Path, section_name: str, item: Dict[str, Any]) -> bool:
    """Add an item to a list section in experiment config YAML. Returns True if added.

    If an item with the same ``name`` already exists it is replaced in-place;
    otherwise the new item is appended.
    """
    try:
        data = load_yaml_ruamel(str(config_path))
        if data is None:
            data = {}

        experiment = data.setdefault("experiment", {})
        items = experiment.setdefault(section_name, [])

        # Replace existing entry with same name, or append
        name = item.get("name")
        if name:
            replaced = False
            for i, existing in enumerate(items):
                if isinstance(existing, dict) and existing.get("name") == name:
                    items[i] = item
                    replaced = True
                    break
            if not replaced:
                items.append(item)
        else:
            items.append(item)

        write_yaml_ruamel(str(config_path), data)
        return True
    except Exception:
        return False
