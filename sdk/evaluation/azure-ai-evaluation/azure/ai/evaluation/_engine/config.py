"""Configuration models with YAML loading support."""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


# Environment variable interpolation
_ENV_VAR_PATTERN = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:(?P<op>:-|-)(?P<arg>.*?))?\}")


def _resolve_env_vars(value: str) -> str:
    """Replace POSIX-style env var references: ${VAR}, ${VAR:-default}, ${VAR-default}."""

    def _replace(m: re.Match) -> str:
        name = m.group("name")
        op = m.group("op")
        arg = m.group("arg") or ""

        is_set = name in os.environ
        v = os.environ.get(name, "")

        if op is None:
            if not is_set:
                raise ValueError(f"Missing required env var: {name}")
            return v
        if op == ":-":
            return v if (is_set and v != "") else arg
        if op == "-":
            return v if is_set else arg

        return m.group(0)

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _interpolate_env_vars(value: Any) -> Any:
    """Recursively interpolate env vars in config structure."""
    if isinstance(value, str):
        return _resolve_env_vars(value)
    if isinstance(value, dict):
        return {k: _interpolate_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env_vars(item) for item in value]
    return value


# Config models
class ConnectionConfig(BaseModel):
    """Configuration for a connection (e.g., Azure OpenAI endpoint)."""

    model_config = ConfigDict(extra="allow")

    name: str


class DatasetConfig(BaseModel):
    """Dataset configuration."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str
    version: str = "1.0.0"
    args: Dict[str, Any] = Field(default_factory=dict)


class EvaluatorConfig(BaseModel):
    """Evaluator configuration."""

    model_config = ConfigDict(extra="allow")

    name: str
    display_name: Optional[str] = None
    mapping: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_mapping_format(self) -> "EvaluatorConfig":
        """Validate mapping values match 'target.X' or 'dataset.X' format."""
        if self.mapping:
            pattern = re.compile(r"^(target|dataset)\.[^.]+$")
            for field, mapping_val in self.mapping.items():
                if not pattern.match(mapping_val):
                    raise ValueError(
                        f"Invalid mapping '{mapping_val}' for field '{field}' in evaluator '{self.name}': "
                        f"expected format 'target.X' or 'dataset.X'"
                    )
        return self


_VALID_TARGET_TYPES = {"custom", "azure_ai_model", "azure_ai_agent"}


class TargetVariantConfig(BaseModel):
    """Target configuration — supports custom, azure_ai_model, azure_ai_agent types."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str = "custom"  # "custom", "azure_ai_model", "azure_ai_agent"

    # Shared: which connection provides the endpoint (applies to model and agent targets)
    connection_name: str = "default"

    # For custom targets: Cartesian product args
    args: Any = Field(default_factory=list)

    # For azure_ai_model targets
    deployment_name: Any = None  # str or list for cartesian (e.g., ["gpt-4.1-mini", "gpt-4.1"])
    prompts: List[str] = Field(default_factory=list)  # prompt file paths (each produces a separate run)

    # For azure_ai_agent targets
    agent_name: Optional[str] = None
    agent_version: Optional[str] = None
    azure_ai_project: Optional[str] = None  # direct override; otherwise resolved from connection
    instructions: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_args(cls, values: Any) -> Any:
        """Accept args as dict or list of dicts."""
        if isinstance(values, dict) and "args" in values:
            args = values["args"]
            if isinstance(args, dict):
                values["args"] = [args]
        return values

    @model_validator(mode="after")
    def validate_target_type(self) -> "TargetVariantConfig":
        """Validate target type is one of the supported types."""
        if self.type not in _VALID_TARGET_TYPES:
            raise ValueError(
                f"Invalid target type '{self.type}' for target '{self.name}'. "
                f"Supported types: {sorted(_VALID_TARGET_TYPES)}"
            )
        return self


class ComputeConfig(BaseModel):
    """Compute backend configuration."""

    model_config = ConfigDict(extra="allow")

    type: str = "local"  # "local" or "foundry"
    azure_ai_project: Optional[str] = None  # Foundry project endpoint URL


class ExperimentConfig(BaseModel):
    """Experiment configuration."""

    model_config = ConfigDict(extra="allow")

    name: str
    version: str = "1.0"
    description: str = ""
    output_path: str = "output"
    max_workers: Optional[int] = None
    targets: List[TargetVariantConfig] = Field(default_factory=list)
    dataset: Optional[DatasetConfig] = None
    evaluators: List[EvaluatorConfig] = Field(default_factory=list)
    compute: Optional[ComputeConfig] = None
    connections: Any = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_config(cls, values: Any) -> Any:
        """Normalize connections format."""
        if isinstance(values, dict) and "connections" in values:
            conns = values["connections"]
            if isinstance(conns, dict):
                values["connections"] = [
                    {"name": k, **v} if isinstance(v, dict) else {"name": k}
                    for k, v in conns.items()
                ]
        return values


class Config(BaseModel):
    """Root configuration with YAML loading support."""

    model_config = ConfigDict(extra="allow")

    experiment: ExperimentConfig

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        """Load configuration from YAML file with env var interpolation."""
        with open(path) as f:
            data = yaml.safe_load(f)
        if data is None:
            raise ValueError(f"Configuration file '{path}' is empty")
        data = _interpolate_env_vars(data)
        return cls(**data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Load configuration from dictionary."""
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump()

    def deep_validate(self) -> List[str]:
        """Validate config against registered components.

        Checks that referenced targets, evaluators, datasets, and connections
        exist in their respective registries. Call after all components are
        registered to catch configuration errors early.

        :returns: List of validation error messages. Empty list means valid.
        """
        from .decorators import DATASET_REGISTRY, EVALUATOR_REGISTRY, TARGET_REGISTRY
        from .dataset_factory import _ensure_builtin_datasets

        _ensure_builtin_datasets()

        errors: List[str] = []
        exp = self.experiment

        # Validate custom target names against registry
        for target_cfg in exp.targets:
            if target_cfg.type == "custom" and target_cfg.name not in TARGET_REGISTRY:
                errors.append(f"Target '{target_cfg.name}' not found in registry")

        # Validate evaluator names against registry
        for eval_cfg in exp.evaluators:
            if eval_cfg.name not in EVALUATOR_REGISTRY:
                errors.append(f"Evaluator '{eval_cfg.name}' not found in registry")

        # Validate dataset type against registry
        if exp.dataset and exp.dataset.type not in DATASET_REGISTRY:
            errors.append(f"Dataset type '{exp.dataset.type}' not found in registry")

        # Validate connection references for non-custom targets
        conn_names: set[str] = set()
        for c in exp.connections:
            if isinstance(c, ConnectionConfig):
                conn_names.add(c.name)
            elif isinstance(c, dict):
                conn_names.add(c.get("name", ""))

        for target_cfg in exp.targets:
            if target_cfg.type != "custom" and target_cfg.connection_name not in conn_names:
                errors.append(
                    f"Target '{target_cfg.name}' references connection "
                    f"'{target_cfg.connection_name}' which is not defined. "
                    f"Available: {sorted(conn_names)}"
                )

        return errors

