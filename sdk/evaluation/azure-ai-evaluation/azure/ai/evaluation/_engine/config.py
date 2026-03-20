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


class MetricConfig(BaseModel):
    """Metric configuration."""

    model_config = ConfigDict(extra="allow")

    name: str
    display_name: Optional[str] = None
    mapping: Dict[str, str] = Field(default_factory=dict)


class TargetVariantConfig(BaseModel):
    """Target configuration — supports custom, azure_ai_model, azure_ai_agent types."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str = "custom"  # "custom", "azure_ai_model", "azure_ai_agent"

    # For custom targets: Cartesian product args
    args: Any = Field(default_factory=list)

    # For azure_ai_model targets
    deployment_name: Any = None  # str or list for cartesian (e.g., ["gpt-4.1-mini", "gpt-4.1"])
    connection_name: str = "default"  # local execution only: which connection provides the endpoint
    prompts: List[str] = Field(default_factory=list)  # prompt file paths (each produces a separate run)

    # For azure_ai_agent targets (out of scope but defined)
    agent_name: Optional[str] = None
    agent_version: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_args(cls, values: Any) -> Any:
        """Accept args as dict or list of dicts."""
        if isinstance(values, dict) and "args" in values:
            args = values["args"]
            if isinstance(args, dict):
                values["args"] = [args]
        return values


# Backward compat alias
ModelVariantConfig = TargetVariantConfig


class TrackingBackendConfig(BaseModel):
    """Tracking backend configuration."""

    model_config = ConfigDict(extra="allow")

    type: str = "none"  # "none" or "foundry"
    # Foundry-specific settings (used when type="foundry")
    azure_ai_project: Optional[str] = None
    deployment_name: Optional[str] = None


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
    output_path: str = "experiment/output"
    max_workers: Optional[int] = None
    targets: List[TargetVariantConfig] = Field(default_factory=list)
    dataset: Optional[DatasetConfig] = None
    metrics: List[MetricConfig] = Field(default_factory=list)
    compute: Optional[ComputeConfig] = None
    tracking_backend: Optional[TrackingBackendConfig] = None
    connections: Any = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_config(cls, values: Any) -> Any:
        """Normalize connections format and handle models->targets backward compat."""
        if isinstance(values, dict) and "connections" in values:
            conns = values["connections"]
            if isinstance(conns, dict):
                values["connections"] = [
                    {"name": k, **v} if isinstance(v, dict) else {"name": k}
                    for k, v in conns.items()
                ]
        # Backward compat: accept "models" as alias for "targets"
        if isinstance(values, dict) and "models" in values and "targets" not in values:
            values["targets"] = values.pop("models")
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
