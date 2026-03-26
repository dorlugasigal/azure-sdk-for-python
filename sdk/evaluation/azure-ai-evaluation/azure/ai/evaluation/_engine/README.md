# Evaluation Engine (`_engine`)

Internal evaluation engine for `azure-ai-evaluation`. This module provides
the CLI (`local-evals`), configuration loading, component discovery, and
local/remote execution of evaluation experiments.

## Architecture

```
_engine/
├── Control Plane
│   ├── cli/              # Click-based CLI commands
│   ├── config.py         # Pydantic YAML configuration models
│   ├── environment.py    # Detects project venv/conda environments
│   ├── preflight.py      # Pre-run validation checks
│   └── discovery.py      # AST-based component auto-discovery
│
├── Execution Plane
│   ├── runner.py          # ExperimentRunner – selects backend, builds context
│   ├── evaluator.py       # ModelEvaluator – iterates records, runs targets & metrics
│   ├── compute.py         # ComputeBackend base, LocalComputeBackend
│   ├── foundry_compute.py # Remote evaluation via Foundry evals API
│   └── otel_trace_capture.py  # OpenTelemetry instrumentation for agent targets
│
├── Data & Metrics
│   ├── decorators.py      # @metric, @dataset, @target, @model decorators & registries
│   ├── decorator_helpers.py   # Shared parameter-resolution helpers
│   ├── datasets.py        # Built-in JsonlDataset, CsvDataset
│   ├── dataset_factory.py # Factory for creating dataset instances
│   ├── metrics_aggregator.py  # Post-run metric aggregation
│   ├── models.py          # ExecutionContext, InferenceOutput, EvaluationOutput
│   └── progress_tracker.py    # Rich/plain-text progress reporting
│
├── Logging (logging/)
│   ├── logger.py          # Rich-aware dual-handler logger (console + file)
│   └── metrics_logger.py  # Thread-safe JSONL/JSON result persistence
│
└── UI (ui/)               # Browser-based results viewer
```

## CLI Commands

Entry point: `local-evals` (or `python -m azure.ai.evaluation._engine.cli`)

| Command | Description |
|---------|-------------|
| `run` | Execute an evaluation experiment from config |
| `new` | Scaffold a new evaluation project |
| `validate` | Check YAML config syntax (with optional deep validation) |
| `list` | Discover available metrics, targets, datasets |
| `view` | Serve experiment results in browser |
| `clear` | Clean output folders (supports date-range filtering) |
| `compute show/set` | Manage compute backend settings |

## Key Concepts

- **Decorator-based registration**: `@metric`, `@dataset`, `@target`, `@model`
  populate global registries that the runner resolves at experiment time.
- **Config-driven execution**: YAML files (`evals.yaml`) define experiments with
  `${VAR:-default}` environment variable interpolation.
- **Pluggable compute**: `LocalComputeBackend` runs in-process; Foundry backend
  submits to the remote evals API.
- **Environment delegation**: The CLI detects project virtual environments and
  re-executes commands inside them.

## Preserved / External Features

These modules integrate with external Azure services and are preserved from
the original codebase:

- **`foundry_compute.py`** – `run_remote_evaluation()` submits experiments
  to the Foundry evals API.
- **`otel_trace_capture.py`** – `OTelTraceCapture` instruments OpenAI SDK
  calls for agent-based targets.
- **`ui/`** – Browser-based experiment results viewer.

## Running Tests

```bash
cd sdk/evaluation/azure-ai-evaluation

# Run all engine tests (use --confcutdir to skip the root test-proxy conftest)
python -m pytest tests/unittests/test_engine/ \
    --confcutdir=tests/unittests/test_engine -v
```
