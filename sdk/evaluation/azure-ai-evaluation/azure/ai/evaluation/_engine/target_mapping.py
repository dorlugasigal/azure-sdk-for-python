"""Utilities for mapping dataset fields to target inputs and outputs."""
from __future__ import annotations

from typing import Any, Dict


def _apply_target_input_mapping(
    record: Dict[str, Any], mapping: Dict[str, str]
) -> Dict[str, Any]:
    """Apply target input mapping: build mapped input from dataset fields.

    For each mapping entry with a ``dataset.X`` source, the dataset field ``X``
    is copied into the result under the mapping key.  Fields not covered by the
    mapping are passed through unchanged so that existing targets continue to
    work when only a partial mapping is specified.

    :param record: The dataset record to map.
    :type record: dict[str, Any]
    :param mapping: A dictionary mapping parameter names to ``dataset.<field>`` source expressions.
    :type mapping: dict[str, str]
    :returns: The mapped record dictionary.
    :rtype: dict[str, Any]
    """
    if not mapping:
        return record

    input_mapping = {
        param: source_field.split(".", 1)[1]
        for param, source_field in mapping.items()
        if source_field.startswith("dataset.")
    }
    if not input_mapping:
        return record

    mapped: Dict[str, Any] = {}
    for param, dataset_field in input_mapping.items():
        if dataset_field not in record:
            raise KeyError(
                f"Target input mapping: field '{dataset_field}' not found in dataset record. "
                f"Available fields: {list(record.keys())}"
            )
        mapped[param] = record[dataset_field]

    # Pass through unmapped fields so targets that read extra columns still work
    for key, value in record.items():
        if key not in mapped:
            mapped[key] = value

    return mapped


def _apply_target_output_mapping(
    model_output: Dict[str, Any], mapping: Dict[str, str]
) -> Dict[str, Any]:
    """Apply target output mapping: rename target output keys to canonical names.

    For each mapping entry with a ``target.X`` source, the target output field
    ``X`` is renamed to the mapping key (the canonical name the engine expects,
    e.g. ``response``).

    :param model_output: The target output dictionary to remap.
    :type model_output: dict[str, Any]
    :param mapping: A dictionary mapping canonical names to ``target.<field>`` source expressions.
    :type mapping: dict[str, str]
    :returns: The remapped output dictionary.
    :rtype: dict[str, Any]
    """
    if not mapping or not isinstance(model_output, dict):
        return model_output

    output_mapping = {
        canonical: source_field.split(".", 1)[1]
        for canonical, source_field in mapping.items()
        if source_field.startswith("target.")
    }
    if not output_mapping:
        return model_output

    result = dict(model_output)
    for canonical, target_field in output_mapping.items():
        if target_field in result:
            value = result.pop(target_field)
            result[canonical] = value

    return result
