# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Utility functions for generating argument combinations and variant names."""

from __future__ import annotations

from itertools import product
from typing import Any, Dict, List

from .models.config import TargetVariantConfig


def generate_args_combinations(model_cfg: TargetVariantConfig) -> List[Dict[str, Any]]:
    """Generate all argument combinations (Cartesian product)."""
    if not model_cfg.args:
        return [{}]

    arg_dicts = []
    args_list = model_cfg.args if isinstance(model_cfg.args, list) else [model_cfg.args]
    for arg in args_list:
        if isinstance(arg, dict):
            for key, values in arg.items():
                if isinstance(values, list):
                    arg_dicts.append({key: values})
                else:
                    arg_dicts.append({key: [values]})

    if not arg_dicts:
        return [{}]

    keys = [list(d.keys())[0] for d in arg_dicts]
    value_lists = [list(d.values())[0] for d in arg_dicts]

    combinations = []
    for values in product(*value_lists):
        combinations.append(dict(zip(keys, values)))

    return combinations


def generate_variant_name(model_name: str, args: Dict[str, Any]) -> str:
    """Generate unique variant name."""
    if not args:
        return model_name

    suffix = "_".join(f"{k}={v}" for k, v in sorted(args.items()))
    return f"{model_name}__{suffix}"


def simplify_combination_names(
    model_name: str, arg_combinations: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Generate simplified names using only the parameters that vary.

    If args are {"prompt": "baseline", "temp": 0.7, "max_tokens": 200} and
    {"prompt": "few_shot", "temp": 0.7, "max_tokens": 200}, the only varying
    key is "prompt", so names become "model__baseline" and "model__few_shot"
    instead of including all parameters.
    """
    if not arg_combinations:
        return {}

    if len(arg_combinations) == 1:
        name = generate_variant_name(model_name, arg_combinations[0])
        return {name: arg_combinations[0]}

    # Find keys that vary across combinations
    varying_keys = set()
    for key in arg_combinations[0]:
        values = {str(args.get(key)) for args in arg_combinations}
        if len(values) > 1:
            varying_keys.add(key)

    # If nothing varies (shouldn't happen), fall back to full name
    if not varying_keys:
        return {
            generate_variant_name(model_name, args): args
            for args in arg_combinations
        }

    # Build simplified names from varying key=value pairs
    result = {}
    for args in arg_combinations:
        parts = [f"{k}={args.get(k)}" for k in sorted(varying_keys)]
        suffix = "_".join(parts)
        simplified = f"{model_name}__{suffix}" if suffix else model_name
        result[simplified] = args

    return result
