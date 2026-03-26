"""v2.0 evaluate() — ALL paths go through the evee engine."""
from __future__ import annotations
import json
import os
import tempfile
from typing import Any, Callable, Dict, List, Optional


def evaluate_v2(
    data: Optional[str] = None,
    evaluators: Optional[Dict[str, Any]] = None,
    target: Optional[Callable] = None,
    evaluator_config: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
    azure_ai_project: Optional[Any] = None,
    credential: Optional[Any] = None,
    config: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Unified evaluate — everything goes through the evee engine.

    # Local (no model needed)
    evaluate_v2(data="data.jsonl", evaluators={"f1": F1ScoreEvaluator()})

    # Cloud via project (engine auto-configures from Foundry)
    evaluate_v2(
        data="data.jsonl",
        evaluators={"relevance": RelevanceEvaluator},
        azure_ai_project="https://your-foundry.../api/projects/my-project",
    )

    # Config-driven
    evaluate_v2(config="config.yaml")
    """
    if config:
        # Direct config path — engine handles everything
        if azure_ai_project:
            # Inject project connection into the config
            config = _inject_project_into_config(config, azure_ai_project, credential)
        return _run_engine(config)

    if data and evaluators:
        # Programmatic path — build a config and run through engine
        config_path = _build_config_from_args(
            data=data,
            evaluators=evaluators,
            evaluator_config=evaluator_config,
            azure_ai_project=azure_ai_project,
            credential=credential,
        )
        return _run_engine(config_path, cleanup_config=True)

    raise ValueError("Either 'config' or 'data' + 'evaluators' must be provided")


def _run_engine(
    config_path: str, cleanup_config: bool = False
) -> Dict[str, Any]:
    """Run the evee engine with a config file."""
    from azure.ai.evaluation._engine.evaluator import ModelEvaluator
    from azure.ai.evaluation._engine.discovery import discover_components
    discover_components()
    evaluator = ModelEvaluator(config_path=config_path)
    dataset = evaluator.load_dataset()
    result = evaluator.evaluate(dataset)
    if cleanup_config:
        try:
            os.unlink(config_path)
        except Exception:
            pass
    return result


def _build_config_from_args(
    data: str,
    evaluators: Dict[str, Any],
    evaluator_config: Optional[Dict[str, Any]] = None,
    azure_ai_project: Optional[Any] = None,
    credential: Optional[Any] = None,
) -> str:
    """Build a YAML config from programmatic arguments and write to temp file.

    This is how the programmatic API feeds into the engine — no bypass.
    """
    import yaml

    # Determine data format
    data_type = "jsonl" if data.endswith(".jsonl") else "csv"

    # Map evaluator classes to registered @metric names
    CLASS_TO_METRIC = {
        "RelevanceEvaluator": "relevance",
        "F1ScoreEvaluator": "f1_score",
        "CoherenceEvaluator": "coherence",
        "FluencyEvaluator": "fluency",
        "GroundednessEvaluator": "groundedness",
        "SimilarityEvaluator": "similarity",
    }

    # Build metrics from evaluators
    metrics = []
    for name, evaluator in evaluators.items():
        # Resolve the registered metric name
        cls_name = evaluator.__name__ if isinstance(evaluator, type) else type(evaluator).__name__
        metric_name = CLASS_TO_METRIC.get(cls_name, name)
        metric_entry = {"name": metric_name}
        # Use the user's key as display name if different
        if metric_name != name:
            metric_entry["display_name"] = name
        # Get column mapping if provided
        if evaluator_config and name in evaluator_config:
            mapping = evaluator_config[name].get("column_mapping", {})
            # Convert ${data.field} → dataset.field for engine
            engine_mapping = {}
            for param, expr in mapping.items():
                if isinstance(expr, str) and expr.startswith("${") and expr.endswith("}"):
                    field = expr[2:-1]  # strip ${ }
                    if field.startswith("data."):
                        engine_mapping[param] = f"dataset.{field[5:]}"
                    else:
                        engine_mapping[param] = field
                else:
                    engine_mapping[param] = expr
            metric_entry["mapping"] = engine_mapping
        metrics.append(metric_entry)

    # Build connections from azure_ai_project
    connections = {}
    if azure_ai_project:
        endpoint, deployment = _resolve_project(azure_ai_project, credential)
        connections["default"] = {
            "azure_endpoint": endpoint,
            "azure_deployment": deployment,
        }
        print(f"  Connected to project, using model: {deployment}")

    config_data = {
        "experiment": {
            "name": "evaluate_v2",
            "targets": [{"name": "default", "type": "custom", "args": {}}],
            "dataset": {
                "name": "input_data",
                "type": data_type,
                "args": {"data_path": os.path.abspath(data)},
            },
            "metrics": metrics,
        }
    }
    if connections:
        config_data["experiment"]["connections"] = connections

    # Write to temp file
    fd, config_path = tempfile.mkstemp(suffix=".yaml", prefix="eval_v2_")
    with os.fdopen(fd, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)

    return config_path


def _resolve_project(azure_ai_project: Any, credential: Optional[Any] = None) -> tuple:
    """Connect to Foundry project and return (endpoint, deployment_name)."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    if credential is None:
        credential = DefaultAzureCredential()

    if isinstance(azure_ai_project, str):
        client = AIProjectClient(endpoint=azure_ai_project, credential=credential)
    else:
        client = azure_ai_project

    endpoint = client._config.endpoint
    base_endpoint = endpoint.split("/api/projects/")[0] if "/api/projects/" in endpoint else endpoint
    if not base_endpoint.endswith("/"):
        base_endpoint += "/"

    # Discover first deployment
    deployment_name = "gpt-4o"
    try:
        for dep in client.deployments.list():
            deployment_name = dep.name
            break
    except Exception:
        pass

    return base_endpoint, deployment_name


def _inject_project_into_config(config_path: str, azure_ai_project: Any,
                                  credential: Optional[Any] = None) -> str:
    """Read existing config, inject project connection, write to temp file."""
    import yaml

    with open(config_path) as f:
        config_data = yaml.safe_load(f)

    endpoint, deployment = _resolve_project(azure_ai_project, credential)
    if "experiment" not in config_data:
        config_data["experiment"] = {}
    config_data["experiment"]["connections"] = {
        "default": {
            "azure_endpoint": endpoint,
            "azure_deployment": deployment,
        }
    }
    print(f"  Injected project connection: {deployment} @ {endpoint}")

    fd, new_path = tempfile.mkstemp(suffix=".yaml", prefix="eval_v2_project_")
    with os.fdopen(fd, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)

    return new_path
