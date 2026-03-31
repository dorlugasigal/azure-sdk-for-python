# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------
"""Foundry cloud compute backend for remote evaluation via the OpenAI-compatible evals API."""

from __future__ import annotations

import inspect
import json
import logging
import textwrap
import time
from typing import Any, Callable, Dict, List, Optional

from .config import Config

# Mapping from evaluator short names to Foundry built-in evaluator names
EVALUATOR_TO_BUILTIN: Dict[str, str] = {
    "f1_score": "builtin.f1_score",
    "relevance": "builtin.relevance",
    "coherence": "builtin.coherence",
    "fluency": "builtin.fluency",
    "groundedness": "builtin.groundedness",
    "similarity": "builtin.similarity",
    "bleu_score": "builtin.bleu_score",
    "rouge_score": "builtin.rouge_score",
    "meteor_score": "builtin.meteor_score",
    "gleu_score": "builtin.gleu_score",
    "violence": "builtin.violence",
    "sexual": "builtin.sexual",
    "self_harm": "builtin.self_harm",
    "hate_unfairness": "builtin.hate_unfairness",
    "task_adherence": "builtin.task_adherence",
    "tool_call_accuracy": "builtin.tool_call_accuracy",
    "intent_resolution": "builtin.intent_resolution",
    "task_completion": "builtin.task_completion",
    "tool_selection": "builtin.tool_selection",
    "tool_input_accuracy": "builtin.tool_input_accuracy",
    "tool_output_utilization": "builtin.tool_output_utilization",
    "tool_call_success": "builtin.tool_call_success",
    "task_navigation_efficiency": "builtin.task_navigation_efficiency",
}

# NLP-based evaluators that don't need a model deployment
NLP_EVALUATORS = {
    "builtin.f1_score",
    "builtin.bleu_score",
    "builtin.rouge_score",
    "builtin.meteor_score",
    "builtin.gleu_score",
    "builtin.task_navigation_efficiency",
}

_POLL_INTERVAL_SECONDS = 3
_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

# Evaluators on a 1-5 ordinal scale (pass threshold = 3).
# Everything else is 0-1 binary or continuous (pass threshold = 0.5).
_ORDINAL_1_5_EVALUATORS = frozenset({
    "coherence", "relevance", "fluency",
    "intent_resolution", "tool_call_accuracy",
})


def _build_portal_url(endpoint: str, eval_id: str) -> Optional[str]:
    """Build Azure AI Foundry portal URL from endpoint and eval ID.

    Constructs the nextgen portal URL format:
    https://ai.azure.com/nextgen/r/{base64_sub},{rg},,{account},{project}/build/evaluations/{eval_id}
    """
    try:
        import base64
        import re
        import subprocess
        import uuid
        from urllib.parse import urlparse

        parsed = urlparse(endpoint)
        host = parsed.hostname or ""

        # Extract account name from hostname
        account = host.split(".")[0] if host else ""

        # Extract project from path
        path_parts = [p for p in parsed.path.split("/") if p]
        project = ""
        for i, part in enumerate(path_parts):
            if part == "projects" and i + 1 < len(path_parts):
                project = path_parts[i + 1]
                break

        if not account or not project:
            return None

        # Get subscription and resource group via az CLI
        result = subprocess.run(
            ["az", "cognitiveservices", "account", "list",
             "--query", f"[?name=='{account}'].{{sub:id,rg:resourceGroup}}",
             "-o", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        import json as _json
        accounts = _json.loads(result.stdout)
        if not accounts:
            return None

        resource_id = accounts[0].get("sub", "")
        rg = accounts[0].get("rg", "")
        id_match = re.search(r"/subscriptions/([^/]+)/", resource_id)
        sub = id_match.group(1) if id_match else ""

        if not sub or not rg:
            return None

        # Encode subscription ID as base64 (big-endian UUID bytes, no padding)
        sub_uuid = uuid.UUID(sub)
        encoded_sub = base64.urlsafe_b64encode(sub_uuid.bytes).rstrip(b"=").decode()

        # Build nextgen portal URL
        resource_path = f"{encoded_sub},{rg},,{account},{project}"
        return f"https://ai.azure.com/nextgen/r/{resource_path}/build/evaluations/{eval_id}"
    except Exception:
        pass
    return None



def _resolve_project_endpoint(
    config: Config,
    project_endpoint: Optional[str],
) -> str:
    """Determine the Foundry project endpoint from params or config."""
    if project_endpoint:
        return project_endpoint.rstrip("/")

    compute = config.experiment.compute
    if compute and compute.azure_ai_project:
        return compute.azure_ai_project.rstrip("/")

    # Search connections for a project endpoint
    for conn in config.experiment.connections or []:
        endpoint = getattr(conn, "azure_ai_project", None) or getattr(conn, "endpoint", None)
        if endpoint:
            return endpoint.rstrip("/")

    raise ValueError(
        "No Foundry project endpoint found. Provide 'project_endpoint', set "
        "'experiment.compute.azure_ai_project' in the config, or add a connection "
        "with an endpoint."
    )


def _load_records(config: Config) -> List[Dict[str, Any]]:
    """Load JSONL records from the dataset path specified in the config."""
    if not config.experiment.dataset:
        raise ValueError("No dataset configured in the experiment config.")

    dataset_path = config.experiment.dataset.args.get("data_path", "")
    if not dataset_path:
        raise ValueError(
            "Dataset 'data_path' is not set in the experiment config args."
        )

    with open(dataset_path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    if not records:
        raise ValueError(f"Dataset file '{dataset_path}' is empty or contains no valid JSONL lines.")

    return records


def _build_testing_criteria(
    config: Config,
    deployment_name: Optional[str],
    project_client: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Convert configured metrics into Foundry testing_criteria entries.

    Known metrics are mapped to built-in evaluators.  Unknown metrics are
    looked up in ``EVALUATOR_REGISTRY`` and uploaded as code-based custom
    evaluators when *project_client* is available.
    """
    testing_criteria: List[Dict[str, Any]] = []

    for evaluator_config in config.experiment.evaluators:
        builtin_name = EVALUATOR_TO_BUILTIN.get(evaluator_config.name)

        if builtin_name:
            # Known built-in evaluator
            criteria_entry: Dict[str, Any] = {
                "type": "azure_ai_evaluator",
                "name": evaluator_config.display_name or evaluator_config.name,
                "evaluator_name": builtin_name,
            }

            # Convert "dataset.field" / "model.field" -> "{{item.field}}"
            if evaluator_config.mapping:
                data_mapping: Dict[str, str] = {}
                for param, source_ref in evaluator_config.mapping.items():
                    field = source_ref.split(".", 1)[1]
                    data_mapping[param] = f"{{{{item.{field}}}}}"
                criteria_entry["data_mapping"] = data_mapping

            # LLM-based evaluators require a deployment
            if builtin_name not in NLP_EVALUATORS:
                criteria_entry["initialization_parameters"] = {
                    "deployment_name": deployment_name or "gpt-4.1-mini",
                }

        elif project_client:
            # Unknown evaluator — try to upload as custom code-based evaluator
            criteria_entry = _upload_custom_metric(
                evaluator_config, project_client, deployment_name
            )
            if criteria_entry is None:
                raise ValueError(
                    f"Evaluator '{evaluator_config.name}' is not a built-in evaluator and "
                    f"could not be uploaded as a custom evaluator. "
                    f"To run remotely, use only built-in evaluators: "
                    f"{', '.join(sorted(EVALUATOR_TO_BUILTIN.keys()))}. "
                    f"Or run locally with: ev run"
                )
        else:
            raise ValueError(
                f"Evaluator '{evaluator_config.name}' is not supported for remote evaluation. "
                f"Supported evaluators: {', '.join(sorted(EVALUATOR_TO_BUILTIN.keys()))}"
            )

        testing_criteria.append(criteria_entry)

    if not testing_criteria:
        raise ValueError("No metrics configured in the experiment config.")

    return testing_criteria


def _extract_inner_class(wrapper_cls: type) -> Optional[type]:
    """Retrieve the original user class captured by the ``@metric`` wrapper.

    The ``@metric`` decorator defines ``MetricWrapper.__init__`` inside a
    closure that captures the original class as ``cls``.  We inspect the
    closure variables to recover it.
    """
    try:
        closure = inspect.getclosurevars(wrapper_cls.__init__)
        original = closure.nonlocals.get("cls")
        if original is not None:
            return original
    except TypeError:
        pass

    # Fallback: instantiate wrapper and inspect ``self.inner``
    try:
        temp = wrapper_cls({}, None)
        if hasattr(temp, "inner"):
            return type(temp.inner)
    except Exception:  # pylint: disable=broad-except
        pass

    return None


def _get_compute_source(inner_cls: type) -> Optional[str]:
    """Return dedented source of *inner_cls.compute*, renamed to ``_compute``."""
    if not hasattr(inner_cls, "compute"):
        return None
    try:
        raw = inspect.getsource(inner_cls.compute)
        source = textwrap.dedent(raw)
        # Rename to a standalone function (remove ``self`` parameter)
        source = source.replace("def compute(self,", "def _compute(", 1)
        source = source.replace("def compute(self ,", "def _compute(", 1)
        source = source.replace("self.", "")
        return source
    except (OSError, TypeError):
        return None


def _build_grade_code(
    evaluator_name: str,
    compute_source: str,
    mapping: Dict[str, str],
) -> str:
    """Synthesise a ``grade(sample, item)`` function that Foundry can execute."""
    field_extractions: List[str] = []
    compute_args: List[str] = []
    for param, source_ref in mapping.items():
        field = source_ref.split(".", 1)[1] if "." in source_ref else source_ref
        field_extractions.append(f'    {param} = item.get("{param}", "") or item.get("{field}", "")')
        compute_args.append(param)

    extractions_str = "\n".join(field_extractions)
    args_str = ", ".join(f"{a}={a}" for a in compute_args)

    grade_code = (
        f"def grade(sample: dict, item: dict) -> float:\n"
        f'    """Auto-generated from @metric(\'{evaluator_name}\')."""\n'
        f"    try:\n"
        f"        # Try all possible locations where data might be\n"
    )

    for param in compute_args:
        field = None
        for p, s in mapping.items():
            if p == param:
                field = s.split(".", 1)[1] if "." in s else s
                break
        grade_code += (
            f"        {param} = (\n"
            f"            item.get(\"{param}\", \"\") or\n"
            f"            item.get(\"{field}\", \"\") or\n"
            f"            item.get(\"sample.output_text\", \"\") or\n"
            f"            (item.get(\"sample\", {{}}) or {{}}).get(\"output_text\", \"\") or\n"
            f"            (sample.get(\"output_text\", \"\") if sample else \"\")\n"
            f"        )\n"
        )

    grade_code += (
        f"\n"
        f"        result = _compute({args_str})\n"
        f"\n"
        f"        if isinstance(result, (int, float)):\n"
        f"            return float(result)\n"
        f"        if isinstance(result, dict):\n"
        f"            for key, val in result.items():\n"
        f"                if isinstance(val, (int, float)):\n"
        f"                    return float(val)\n"
        f"        return 0.0\n"
        f"    except Exception as _exc:\n"
        f"        raise ValueError(\n"
        f"            f\"Grading failed for '{evaluator_name}': {{_exc}}. \"\n"
        f"            f\"sample keys={{list(sample.keys()) if sample else []}}, \"\n"
        f"            f\"item keys={{list(item.keys()) if item else []}}\"\n"
        f"        ) from _exc\n"
    )

    return compute_source + "\n\n" + grade_code


def _upload_custom_metric(
    evaluator_config: Any,
    project_client: Any,
    deployment_name: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Upload a custom ``@metric`` as a code-based evaluator to Foundry catalog.

    Synthesises a ``grade(sample, item)`` function from the evaluator's
    ``compute()`` method and registers it via
    ``project_client.beta.evaluators.create_version()``.
    """
    from .decorators import EVALUATOR_REGISTRY

    logger = logging.getLogger(__name__)

    evaluator_name = evaluator_config.name
    wrapper_cls = EVALUATOR_REGISTRY.get(evaluator_name)
    if not wrapper_cls:
        return None

    inner_cls = _extract_inner_class(wrapper_cls)
    if inner_cls is None:
        logger.warning("Could not extract inner class for evaluator '%s'.", evaluator_name)
        return None

    compute_source = _get_compute_source(inner_cls)
    if compute_source is None:
        logger.warning("Could not retrieve compute() source for evaluator '%s'.", evaluator_name)
        return None

    mapping = evaluator_config.mapping or {}
    full_code = _build_grade_code(evaluator_name, compute_source, mapping)

    # Build data schema from mapping — use param names (what grade() reads)
    data_schema_props: Dict[str, Any] = {}
    for param, source_ref in mapping.items():
        data_schema_props[param] = {"type": "string"}

    try:
        from azure.ai.projects.models import (  # type: ignore[import-untyped]
            EvaluatorCategory,
            EvaluatorDefinitionType,
        )

        result = project_client.beta.evaluators.create_version(
            name=evaluator_name,
            evaluator_version={
                "name": evaluator_name,
                "categories": [EvaluatorCategory.QUALITY],
                "display_name": evaluator_name,
                "description": f"Custom evaluator: {evaluator_name}",
                "definition": {
                    "type": EvaluatorDefinitionType.CODE,
                    "code_text": full_code,
                    "init_parameters": {
                        "type": "object",
                        "properties": {
                            "deployment_name": {"type": "string"},
                            "pass_threshold": {"type": "number"},
                        },
                        "required": ["deployment_name", "pass_threshold"],
                    },
                    "metrics": {
                        "result": {
                            "type": "continuous",
                            "desirable_direction": "increase",
                        }
                    },
                    "data_schema": {
                        "type": "object",
                        "required": ["item"],
                        "properties": {
                            "item": {
                                "type": "object",
                                "properties": data_schema_props,
                            },
                        },
                    },
                },
            },
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Failed to upload custom evaluator '%s': %s", evaluator_name, exc)
        return None

    criteria_entry: Dict[str, Any] = {
        "type": "azure_ai_evaluator",
        "name": evaluator_name,
        "evaluator_name": evaluator_name,
        "initialization_parameters": {
            "deployment_name": deployment_name or "gpt-4.1-mini",
            "pass_threshold": 3.0 if evaluator_name in _ORDINAL_1_5_EVALUATORS else 0.5,
        },
    }

    if mapping:
        data_mapping: Dict[str, str] = {}
        for param, source_ref in mapping.items():
            field = source_ref.split(".", 1)[1] if "." in source_ref else source_ref
            data_mapping[param] = "{{item." + field + "}}"
        criteria_entry["data_mapping"] = data_mapping

    return criteria_entry


def _build_data_source_config(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build an eval data source config with schema inferred from the first record."""
    properties = {key: {"type": "string"} for key in records[0]}
    return {
        "type": "custom",
        "item_schema": {
            "type": "object",
            "properties": properties,
            "required": list(records[0].keys()),
        },
        "include_sample_schema": True,
    }


def run_remote_evaluation(
    config_path: str,
    project_endpoint: Optional[str] = None,
    credential: Optional[Any] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Submit an evaluation to Azure AI Foundry cloud compute and return results.

    :param config_path: Path to the experiment YAML configuration file.
    :param project_endpoint: Azure AI Foundry project endpoint URL. Falls back to
        the value in the config if not provided.
    :param credential: Azure credential instance. Defaults to
        ``DefaultAzureCredential()`` when not set.
    :param on_progress: Optional callback invoked with status messages during
        execution (useful for CLI progress display).
    :returns: A dict containing status, eval/run IDs, result counts, and output items.
    :raises ImportError: If ``azure-ai-projects`` or ``azure-identity`` is not installed.
    :raises ValueError: If the config is missing required fields.
    """

    def _progress(msg: str) -> None:
        if on_progress is not None:
            on_progress(msg)

    # --- Load config & data ------------------------------------------------
    _progress("Loading experiment configuration...")
    config = Config.from_yaml(config_path)

    endpoint = _resolve_project_endpoint(config, project_endpoint)
    _progress(f"Using Foundry endpoint: {endpoint}")

    records = _load_records(config)
    _progress(f"Loaded {len(records)} records from dataset.")

    # --- Build eval params -------------------------------------------------
    data_source_config = _build_data_source_config(records)

    # --- Connect to Foundry ------------------------------------------------
    _progress("Connecting to Azure AI Foundry...")

    try:
        from azure.ai.projects import AIProjectClient  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "The 'azure-ai-projects' package is required for Foundry remote evaluation. "
            "Install it with: pip install azure-ai-projects"
        ) from exc

    if credential is None:
        try:
            from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]

            credential = DefaultAzureCredential()
        except ImportError as exc:
            raise ImportError(
                "The 'azure-identity' package is required for default credential support. "
                "Install it with: pip install azure-identity"
            ) from exc

    try:
        project_client = AIProjectClient(endpoint=endpoint, credential=credential)
        openai_client = project_client.get_openai_client()
    except Exception as exc:
        raise RuntimeError(
            f"Failed to connect to Azure AI Foundry at '{endpoint}': {exc}"
        ) from exc

    # --- Build testing criteria (needs project_client for custom metrics) ---
    from .discovery import discover_components

    discover_components()

    # Derive deployment_name for LLM-based evaluators from azure_ai_model targets
    _evaluator_deployment = None
    for t in config.experiment.targets:
        if getattr(t, "type", "custom") == "azure_ai_model":
            dep = t.deployment_name
            if isinstance(dep, list) and dep:
                _evaluator_deployment = dep[0]
            elif isinstance(dep, str):
                _evaluator_deployment = dep
            break
    testing_criteria = _build_testing_criteria(config, _evaluator_deployment, project_client=project_client)

    # --- Expand model variants (Cartesian product) --------------------------
    from itertools import product as itertools_product

    def _expand_variants(cfg: Config) -> List[Dict[str, Any]]:
        """Expand target configs into variant combinations, respecting target types."""
        variants = []
        for target_cfg in cfg.experiment.targets:
            target_type = getattr(target_cfg, "type", "custom")

            if target_type == "azure_ai_model":
                # Expand both deployment_name (list) AND args (cartesian) together
                dep_names = target_cfg.deployment_name
                if isinstance(dep_names, str):
                    dep_names = [dep_names]
                elif not dep_names:
                    dep_names = ["gpt-4.1-mini"]

                # Build cartesian dimensions: deployment_name + any extra args
                arg_dicts = [{"deployment_name": dep_names}]
                extra_args = target_cfg.args if isinstance(target_cfg.args, list) else (
                    [target_cfg.args] if target_cfg.args else []
                )
                for arg in extra_args:
                    if isinstance(arg, dict):
                        for key, values in arg.items():
                            if isinstance(values, list):
                                arg_dicts.append({key: values})
                            else:
                                arg_dicts.append({key: [values]})

                keys = [list(d.keys())[0] for d in arg_dicts]
                value_lists = [list(d.values())[0] for d in arg_dicts]
                for values in itertools_product(*value_lists):
                    combo = dict(zip(keys, values))
                    variants.append({
                        "_model": target_cfg.name,
                        "_args": combo,
                        "_type": "azure_ai_model",
                        "_target_cfg": target_cfg,
                    })
            elif target_type == "azure_ai_agent":
                variants.append({
                    "_model": target_cfg.name,
                    "_args": {},
                    "_type": "azure_ai_agent",
                    "_target_cfg": target_cfg,
                })
            else:
                # Custom targets — expand args as before
                args_list = target_cfg.args if isinstance(target_cfg.args, list) else (
                    [target_cfg.args] if target_cfg.args else [{}]
                )
                arg_dicts = []
                for arg in args_list:
                    if isinstance(arg, dict):
                        for key, values in arg.items():
                            if isinstance(values, list):
                                arg_dicts.append({key: values})
                            else:
                                arg_dicts.append({key: [values]})
                if not arg_dicts:
                    variants.append({
                        "_model": target_cfg.name,
                        "_args": {},
                        "_type": "custom",
                        "_target_cfg": target_cfg,
                    })
                    continue
                keys = [list(d.keys())[0] for d in arg_dicts]
                value_lists = [list(d.values())[0] for d in arg_dicts]
                for values in itertools_product(*value_lists):
                    combo = dict(zip(keys, values))
                    variants.append({
                        "_model": target_cfg.name,
                        "_args": combo,
                        "_type": "custom",
                        "_target_cfg": target_cfg,
                    })
        return variants

    variants = _expand_variants(config)
    # If no models configured (pure dataset eval), default to a single variant
    if not variants:
        variants = [{"_model": "default", "_args": {}, "_type": "custom"}]
    has_multiple_variants = len(variants) > 1

    if has_multiple_variants:
        # Find varying keys for simplified names
        all_keys = set()
        for v in variants:
            all_keys.update(v["_args"].keys())
        varying_keys = set()
        for key in all_keys:
            vals = {str(v["_args"].get(key)) for v in variants}
            if len(vals) > 1:
                varying_keys.add(key)

        def _variant_name(v: Dict[str, Any]) -> str:
            if varying_keys:
                parts = [f"{k}={v['_args'][k]}" for k in sorted(varying_keys) if k in v["_args"]]
                return ", ".join(parts) if parts else v["_model"]
            return v["_model"]

        _progress(f"Expanding {len(variants)} model variants...")

    # --- Remap response fields for model/agent targets ---------------------
    # Must happen BEFORE eval creation since testing_criteria are baked into the eval
    query_field = None
    has_model_targets = any(v.get("_type") in ("azure_ai_model", "azure_ai_agent") for v in variants)
    has_agent_targets = any(v.get("_type") == "azure_ai_agent" for v in variants)
    if has_model_targets:
        for field in ["query", "question", "prompt", "input"]:
            if field in records[0]:
                query_field = field
                break
        if not query_field:
            query_field = list(records[0].keys())[0]

        # Update testing criteria: response mappings → model/agent output
        for criteria in testing_criteria:
            if "data_mapping" in criteria:
                for param in list(criteria["data_mapping"].keys()):
                    if param == "response":
                        current = criteria["data_mapping"][param]
                        if "output_items" in current:
                            # Explicitly mapped to output_items in YAML — keep it
                            criteria["data_mapping"][param] = "{{sample.output_items}}"
                        else:
                            # Text-based evaluators get the final answer text
                            criteria["data_mapping"][param] = "{{sample.output_text}}"

    # --- Create evaluation -------------------------------------------------
    _progress("Creating evaluation...")

    try:
        eval_object = openai_client.evals.create(
            name=config.experiment.name,
            data_source_config=data_source_config,
            testing_criteria=testing_criteria,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to create evaluation: {exc}") from exc

    _progress(f"Evaluation created: {eval_object.id}")

    # --- Submit runs -------------------------------------------------------
    _progress("Submitting evaluation run(s)...")

    try:
        from openai.types.evals.create_eval_jsonl_run_data_source_param import (
            CreateEvalJSONLRunDataSourceParam,
            SourceFileContent,
            SourceFileContentContent,
        )

        def _submit_one_run(variant_name: str, variant: Dict[str, Any]) -> Any:
            """Submit a single run (dataset or model target)."""
            variant_args = variant["_args"]
            variant_type = variant.get("_type", "custom")
            target_cfg = variant.get("_target_cfg")

            if variant_type in ("azure_ai_model", "azure_ai_agent"):
                # Model/agent target evaluation
                # Build input messages template
                template_messages = []

                # Add developer/system instructions if configured
                if target_cfg and hasattr(target_cfg, 'instructions') and target_cfg.instructions:
                    template_messages.append({
                        "type": "message",
                        "role": "developer",
                        "content": {
                            "type": "input_text",
                            "text": target_cfg.instructions,
                        },
                    })

                template_messages.append({
                    "type": "message",
                    "role": "user",
                    "content": {
                        "type": "input_text",
                        "text": "{{item." + query_field + "}}",
                    },
                })

                input_messages: Dict[str, Any] = {
                    "type": "template",
                    "template": template_messages,
                }

                if variant_type == "azure_ai_agent":
                    run_target: Dict[str, Any] = {
                        "type": "azure_ai_agent",
                        "name": target_cfg.agent_name or target_cfg.name,
                    }
                    if target_cfg.agent_version:
                        run_target["version"] = target_cfg.agent_version
                else:
                    effective_model = variant_args.get("deployment_name", "gpt-4.1-mini")
                    run_target = {
                        "type": "azure_ai_model",
                        "model": effective_model,
                    }
                    # Apply sampling params from variant args
                    _SAMPLING_KEYS = {
                        "temperature": float,
                        "top_p": float,
                        "max_completion_tokens": int,
                        "max_tokens": int,  # mapped to max_completion_tokens
                        "frequency_penalty": float,
                        "presence_penalty": float,
                        "seed": int,
                    }
                    sampling = {}
                    for key, cast in _SAMPLING_KEYS.items():
                        if key in variant_args:
                            api_key = "max_completion_tokens" if key == "max_tokens" else key
                            sampling[api_key] = cast(variant_args[key])
                    if sampling:
                        run_target["sampling_params"] = sampling

                return openai_client.evals.runs.create(
                    eval_id=eval_object.id,
                    name=variant_name,
                    data_source={
                        "type": "azure_ai_target_completions",
                        "source": SourceFileContent(
                            type="file_content",
                            content=[SourceFileContentContent(item=r) for r in records],
                        ),
                        "input_messages": input_messages,
                        "target": run_target,
                    },
                )
            else:
                # Dataset evaluation (custom targets)
                return openai_client.evals.runs.create(
                    eval_id=eval_object.id,
                    name=variant_name,
                    data_source=CreateEvalJSONLRunDataSourceParam(
                        type="jsonl",
                        source=SourceFileContent(
                            type="file_content",
                            content=[SourceFileContentContent(item=r) for r in records],
                        ),
                    ),
                )

        # Submit all variant runs
        submitted_runs = []
        for i, variant in enumerate(variants):
            vname = _variant_name(variant) if has_multiple_variants else f"{config.experiment.name}_run"
            _progress(f"Submitting run '{vname}' ({i + 1}/{len(variants)})...")
            run_obj = _submit_one_run(vname, variant)
            submitted_runs.append((vname, run_obj))
            _progress(f"Run submitted: {run_obj.id}")

    except Exception as exc:
        raise RuntimeError(f"Failed to submit evaluation run: {exc}") from exc

    # --- Poll for completion (all runs in parallel) -------------------------
    completed_runs = []
    completed_names = []
    pending = {vname: eval_run for vname, eval_run in submitted_runs}
    total_runs = len(pending)

    while pending:
        still_pending = {}
        for vname, eval_run in pending.items():
            try:
                run = openai_client.evals.runs.retrieve(
                    run_id=eval_run.id,
                    eval_id=eval_object.id,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to retrieve run status for run '{eval_run.id}': {exc}"
                ) from exc

            if run.status in _TERMINAL_STATUSES:
                completed_names.append(vname)
                completed_runs.append((vname, eval_run, run))
            else:
                still_pending[vname] = eval_run

        # Build status display: ✓ for completed, ⠿ for pending
        lines = []
        for vname, _ in submitted_runs:
            if vname in completed_names:
                lines.append(f"  ✓ {vname}")
            elif vname in still_pending:
                lines.append(f"  ⠿ {vname}  (in progress)")
        status_text = "\n".join(lines)
        _progress(f"Runs ({len(completed_names)}/{total_runs} complete):\n{status_text}")

        if still_pending:
            time.sleep(_POLL_INTERVAL_SECONDS)
        pending = still_pending

    _progress("All runs complete.")

    # --- Collect results ---------------------------------------------------
    portal_url = _build_portal_url(endpoint, eval_object.id)
    last_vname, last_eval_run, last_run = completed_runs[-1]

    results: Dict[str, Any] = {
        "status": last_run.status,
        "eval_id": eval_object.id,
        "run_id": last_eval_run.id,
        "report_url": portal_url or getattr(last_run, "report_url", None),
        "result_counts": getattr(last_run, "result_counts", None),
        "total_records": len(records) * len(variants),
        "variants": len(variants),
        "output_items": [],
    }

    # Retrieve output items from last run
    if last_run.status == "completed":
        _progress("Retrieving output items...")
        try:
            output_items = list(
                openai_client.evals.runs.output_items.list(
                    run_id=last_eval_run.id,
                    eval_id=eval_object.id,
                )
            )
            results["output_items"] = [
                {
                    "item": getattr(item, "item", {}),
                    "results": (
                        getattr(item, "results", [])
                        if hasattr(item, "results")
                        else getattr(item, "result", {})
                    ),
                }
                for item in output_items
            ]
        except Exception as exc:
            _progress(f"Warning: failed to retrieve output items: {exc}")

    # --- Keep eval visible in portal (do NOT delete) -------------------------

    _progress("Remote evaluation complete.")
    return results
