# local-evals Demo

## Architecture

![local-evals Architecture](local-evals-architecture.drawio.png)

> 📐 Editable source: [local-evals-architecture.drawio](local-evals-architecture.drawio) (open in [draw.io](https://app.diagrams.net/))

local-evals separates **compute** (where evaluation runs) from **tracking** (where results are published). When `targets:` is omitted, the engine scores dataset fields directly — no target needed. When present, targets define **what** is being evaluated — either a custom `@target` class (`type: custom`) or a Foundry-deployed model (`type: azure_ai_model`) that generates responses at runtime.

| Mode | Compute | Tracking | Use Case |
|------|---------|----------|----------|
| Local only | Your machine | None | Quick iteration, no cloud needed |
| Mixed metrics | Your machine | None | Local F1 + cloud Relevance (LLM-as-judge) |
| Local + Tracking | Your machine | Foundry portal | Run locally, view results in Foundry |
| Remote dataset eval | Foundry cloud | Foundry portal | Evaluate pre-computed responses on Foundry |
| Remote model target | Foundry cloud | Foundry portal | Send queries to deployed model, evaluate responses |
| Prompt comparison | Your machine | None | Cartesian product over prompt strategies |

> **Note:** Agent evaluation (`type: azure_ai_agent`) is out of scope — it requires a unified approach for tool calls, structured output, and conversation history.

---

## 1. Local-Only Evaluation

**No Azure credentials needed.** Runs F1 score (NLP metric) entirely locally. No `targets:` needed — when omitted, the engine scores the dataset directly.
```bash
local-evals run -c demo/evals_local.yaml --no-tracking
```

<details>
<summary>evals_local.yaml</summary>

```yaml
experiment:
  name: "local-only-eval"

  dataset:
    name: "qa_data"
    type: "jsonl"
    args:
      data_path: "demo/data.jsonl"

  metrics:
    - name: "f1_score"                   # local NLP metric — no LLM call
      mapping:
        response: "dataset.answer"
        ground_truth: "dataset.context"
```
</details>

---

## 2. Mixed Evaluation (Local + Cloud Metrics)

Combines **local** F1 score with **cloud** Relevance (LLM-as-judge via Azure OpenAI). No `targets:` needed — the engine scores the dataset directly. Requires `az login`.
```bash
local-evals run -c demo/evals_mixed.yaml --no-tracking
```

<details>
<summary>evals_mixed.yaml</summary>

```yaml
experiment:
  name: "mixed-eval-demo"

  dataset:
    name: "qa_data"
    type: "jsonl"
    args:
      data_path: "demo/data.jsonl"

  metrics:
    - name: "f1_score"                   # LOCAL — computed in-process
      mapping:
        response: "dataset.answer"
        ground_truth: "dataset.context"
    - name: "relevance"                  # CLOUD — calls Azure OpenAI (LLM-as-judge)
      mapping:
        query: "dataset.question"
        response: "dataset.answer"

  connections:
    default:
      azure_endpoint: "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/"
      azure_deployment: "gpt-4.1-mini"
```
</details>

---

## 3. Local Compute + Foundry Tracking

Evaluation runs **locally** on your machine, but results are **published to Azure AI Foundry** so you can view them in the portal. This is the `tracking_backend` pattern — separate from compute.
```bash
local-evals run -c demo/evals_tracking.yaml
```

<details>
<summary>evals_tracking.yaml</summary>

```yaml
experiment:
  name: "local-eval-with-foundry-tracking"

  tracking_backend:                      # ← publishes results to Foundry portal
    type: "foundry"
    azure_ai_project: "https://foundry-evee-ko9z2s7c.services.ai.azure.com/api/projects/foundry-project-evee-ko9z2s7c"

  dataset:
    name: "qa_data"
    type: "jsonl"
    args:
      data_path: "demo/data.jsonl"

  metrics:
    - name: "f1_score"
      mapping:
        response: "dataset.answer"
        ground_truth: "dataset.context"
    - name: "relevance"
      mapping:
        query: "dataset.question"
        response: "dataset.answer"

  connections:
    default:
      azure_endpoint: "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/"
      azure_deployment: "gpt-4.1-mini"
```
</details>

Key difference from remote: `tracking_backend` (publishes results) vs `compute` (runs evaluation). Here evaluation runs locally but results appear in the Foundry Evaluations UI.

---

## 4. Remote Compute (Foundry Cloud)

The **entire evaluation** is submitted to Azure AI Foundry cloud. Foundry runs the evaluators and stores results. Use `--remote` flag.
```bash
local-evals run -c demo/evals_remote.yaml --remote
```

<details>
<summary>evals_remote.yaml</summary>

```yaml
experiment:
  name: "foundry-cloud-eval"

  compute:                               # ← evaluation RUNS on Foundry cloud
    type: "foundry"
    azure_ai_project: "https://foundry-evee-ko9z2s7c.services.ai.azure.com/api/projects/foundry-project-evee-ko9z2s7c"

  dataset:
    name: "qa_data"
    type: "jsonl"
    args:
      data_path: "demo/data.jsonl"

  metrics:
    - name: "f1_score"
      mapping:
        response: "dataset.answer"
        ground_truth: "dataset.context"
    - name: "relevance"
      mapping:
        query: "dataset.question"
        response: "dataset.answer"

  connections:
    default:
      azure_endpoint: "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/"
      azure_deployment: "gpt-4.1-mini"
```
</details>

---

## 5. Prompt Comparison (Cartesian Product)

Evaluates multiple prompt strategies (baseline, single-shot, few-shot) × temperature combinations in a Cartesian product. Uses a custom `@target` class that calls GPT-4.1-mini.
```bash
local-evals run -c demo/prompt_comparison.yaml --no-tracking
```

<details>
<summary>prompt_comparison.yaml</summary>

```yaml
experiment:
  name: "prompt-strategy-comparison"

  targets:
    - name: "prompt_compare"         # custom @target in prompt_models.py
      type: "custom"
      args:
        - prompt: ["baseline", "single_shot", "few_shot"]   # 3 strategies
        - temperature: [0.7]
        - max_tokens: [200]
        # Cartesian product: 3 × 1 × 1 = 3 target variants

  dataset:
    name: "qa_data"
    type: "jsonl"
    args:
      data_path: "demo/data.jsonl"

  metrics:
    - name: "relevance"
      mapping:
        query: "dataset.question"
        response: "model.answer"     # ← maps to model output field
        context: "dataset.context"
    - name: "f1_score"
      mapping:
        response: "model.answer"
        ground_truth: "dataset.context"

  connections:
    default:
      azure_endpoint: "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/"
      azure_deployment: "gpt-4.1-mini"
```
</details>

---

## 6. Remote Model Target Evaluation

Sends queries to a **Foundry-deployed model** and evaluates the generated responses in the cloud. Unlike dataset evaluation, the target generates responses at runtime.
```bash
local-evals run -c demo/evals_remote_model.yaml --remote
```

<details>
<summary>evals_remote_model.yaml</summary>

```yaml
experiment:
  name: "remote-model-eval"

  compute:
    type: "foundry"
    azure_ai_project: "https://foundry-evee-ko9z2s7c.services.ai.azure.com/api/projects/foundry-project-evee-ko9z2s7c"

  targets:
    - name: "foundry_model"
      type: "azure_ai_model"
      deployment_name: "gpt-4.1-mini"
      connection_name: "default"

  dataset:
    name: "qa_data"
    type: "jsonl"
    args:
      data_path: "demo/data.jsonl"

  metrics:
    - name: "relevance"
      mapping:
        query: "dataset.question"
        response: "model.answer"       # mapped to {{sample.output_text}} on Foundry
    - name: "coherence"
      mapping:
        query: "dataset.question"
        response: "model.answer"

  connections:
    default:
      azure_endpoint: "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/"
      azure_deployment: "gpt-4.1-mini"
```
</details>

Key difference from dataset evaluation: here the `azure_ai_model` target tells Foundry to send each query to gpt-4.1-mini and evaluate the live response. The `response` mapping is automatically remapped to `{{sample.output_text}}` (the model's generated output).

---

## 7. Remote Cartesian Product

Compare multiple parameter variants **on Foundry cloud**. Expands the Cartesian product locally, creates 1 eval, and submits each variant as a separate run for side-by-side comparison in the portal.

```bash
local-evals run -c demo/evals_remote_cartesian.yaml --remote
```

<details>
<summary>evals_remote_cartesian.yaml</summary>

```yaml
experiment:
  name: "remote-prompt-comparison"

  compute:
    type: "foundry"
    azure_ai_project: "https://foundry-evee-ko9z2s7c.services.ai.azure.com/api/projects/foundry-project-evee-ko9z2s7c"

  targets:
    - name: "temperature_comparison"
      type: "azure_ai_model"
      deployment_name: "gpt-4.1-mini"
      connection_name: "default"
      args:
        - temperature: [0.3, 0.7, 1.0]    # 3 variants → 3 Foundry runs

  dataset:
    name: "qa_data"
    type: "jsonl"
    args:
      data_path: "demo/data.jsonl"

  metrics:
    - name: "relevance"
      mapping:
        query: "dataset.question"
        response: "model.answer"
    - name: "coherence"
      mapping:
        query: "dataset.question"
        response: "model.answer"

  connections:
    default:
      azure_endpoint: "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/"
      azure_deployment: "gpt-4.1-mini"
```
</details>

Each variant (temperature=0.3, 0.7, 1.0) becomes a separate run under the same eval. The Foundry portal shows them side-by-side with "Compare runs" for statistical comparison.

---

## 8. Model Comparison (Multi-Deployment)

Compare **different models and sampling parameters** side-by-side. Uses cartesian product across `deployment_name` and `args` — each combination becomes a separate run under the same eval.

```bash
# Run locally (uses connection endpoint + bearer token auth)
local-evals run -c demo/evals_model_comparison.yaml --no-tracking

# Or run on Foundry cloud
local-evals run -c demo/evals_model_comparison.yaml --remote
```

<details>
<summary>evals_model_comparison.yaml</summary>

```yaml
experiment:
  name: "model-comparison"

  compute:
    type: "foundry"
    azure_ai_project: "https://..."

  targets:
    - name: "model_compare"
      type: "azure_ai_model"
      deployment_name: ["gpt-4.1-mini", "gpt-4.1"]   # 2 models
      connection_name: "default"                       # for local execution only
      args:
        - temperature: [0.3, 0.9]                     # × 2 temps = 4 runs total

  dataset:
    name: "qa_data"
    type: "jsonl"
    args:
      data_path: "demo/data.jsonl"

  metrics:
    - name: "relevance"
      mapping:
        query: "dataset.question"
        response: "model.answer"
    - name: "coherence"
      mapping:
        query: "dataset.question"
        response: "model.answer"

  connections:
    default:
      azure_endpoint: "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/"
      azure_deployment: "gpt-4.1-mini"
```
</details>

**How it works:**
- `deployment_name` + `args` are combined as cartesian product (2 models × 2 temperatures = 4 runs)
- **Locally**: each variant calls the OpenAI client with the appropriate model + sampling params
- **Remotely** (`--remote`): each variant becomes a Foundry run with `sampling_params` applied
- `connection_name` is only used for local execution — ignored with `--remote`

**Supported sampling parameters** (all usable as cartesian `args`):

| Parameter | Type | Description |
|-----------|------|-------------|
| `temperature` | float | Randomness (0–2, default 1) |
| `top_p` | float | Nucleus sampling (0–1, default 1) |
| `max_completion_tokens` | int | Maximum output tokens |
| `frequency_penalty` | float | Penalize repeated tokens (-2 to 2) |
| `presence_penalty` | float | Penalize repeated topics (-2 to 2) |
| `seed` | int | Deterministic output |

---

## 9. Custom Metric

Create your own `@metric` class — it's auto-discovered from the working directory and runs alongside built-in evaluators.

```bash
local-evals run -c demo/evals_custom_metric.yaml --no-tracking
```

<details>
<summary>custom_metrics.py</summary>

```python
from azure.ai.evaluation._engine.decorators import metric, BaseMetric

@metric(name="answer_length")
class AnswerLengthMetric(BaseMetric):
    """Scores answers by length — prefers concise responses (50-200 chars)."""

    def compute(self, response: str = "", **kwargs):
        length = len(response)
        if length == 0:
            score = 0.0
        elif length < 50:
            score = 0.5
        elif length <= 200:
            score = 1.0
        else:
            score = max(0.3, 1.0 - (length - 200) / 500)
        return {"answer_length_score": round(score, 3), "answer_length_chars": length}

    def aggregate(self, scores):
        vals = [s["answer_length_score"] for s in scores]
        chars = [s["answer_length_chars"] for s in scores]
        return {
            "answer_length_score_mean": round(sum(vals) / len(vals), 3),
            "answer_length_chars_mean": round(sum(chars) / len(chars), 1),
        }
```
</details>

<details>
<summary>evals_custom_metric.yaml</summary>

```yaml
experiment:
  name: "custom-metric-demo"

  dataset:
    name: "qa_data"
    type: "jsonl"
    args:
      data_path: "demo/data.jsonl"

  metrics:
    - name: "f1_score"                     # built-in
      mapping:
        response: "dataset.answer"
        ground_truth: "dataset.context"
    - name: "answer_length"                # custom — auto-discovered from custom_metrics.py
      mapping:
        response: "dataset.answer"
```
</details>

The `@metric` decorator registers the class by name. The engine scans `*.py` files in the working directory for `@metric`, `@target`, and `@dataset` decorators via AST parsing.

---

## 10. Custom Metric on Remote

Run a custom `@metric` on **Foundry cloud** — the engine auto-uploads your `compute()` method as a [code-based custom evaluator](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators) to the Foundry evaluator catalog.

```bash
local-evals run -c demo/evals_custom_metric_remote.yaml --remote
```

<details>
<summary>custom_metrics_remote.py</summary>

```python
from azure.ai.evaluation._engine.decorators import metric, BaseMetric

@metric(name="conciseness")
class ConcisenessMetric(BaseMetric):
    """Scores response conciseness — prefers 50-200 character answers."""

    def compute(self, response: str = "", **kwargs):
        length = len(response)
        if length == 0:
            score = 0.0
        elif length < 50:
            score = 0.5
        elif length <= 200:
            score = 1.0
        else:
            score = max(0.3, 1.0 - (length - 200) / 500)
        return {"conciseness_score": round(score, 3)}

    def aggregate(self, scores):
        vals = [s["conciseness_score"] for s in scores]
        return {"conciseness_score_mean": round(sum(vals) / len(vals), 3)}
```
</details>

<details>
<summary>evals_custom_metric_remote.yaml</summary>

```yaml
experiment:
  name: "custom-metric-remote-demo"

  compute:
    type: "foundry"
    azure_ai_project: "https://..."

  dataset:
    name: "qa_data"
    type: "jsonl"
    args:
      data_path: "demo/data.jsonl"

  metrics:
    - name: "f1_score"                       # built-in → runs as builtin.f1_score
      mapping:
        response: "dataset.answer"
        ground_truth: "dataset.context"
    - name: "conciseness"                    # custom → auto-uploaded to evaluator catalog
      mapping:
        response: "dataset.answer"
```
</details>

**How it works:**
1. The engine finds `conciseness` is not a built-in evaluator
2. Looks up the `@metric` class in the registry, extracts the `compute()` source code
3. Synthesizes a Foundry-compatible `grade(sample, item) -> float` function
4. Uploads it via `project_client.beta.evaluators.create_version()` (code-based evaluator)
5. References it by name in `testing_criteria` alongside the built-in `f1_score`

**Sandbox constraints** for custom metrics on remote:
- Must return a float between 0.0 and 1.0
- No network access at runtime
- Available packages: numpy, pandas, scikit-learn, nltk, rouge-score, pydantic, and [more](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators#supported-packages-and-limits)
- Max 256 KB code, 2 min timeout per item

---

## Capabilities & Limitations

### What runs where

| Component | Local | Remote (Foundry) |
|-----------|-------|-------------------|
| **Built-in metrics** (f1, relevance, etc.) | ✅ Run in-process | ✅ Run as `builtin.*` evaluators |
| **Custom `@metric` classes** | ✅ Full Python flexibility | ⚠️ Possible via code-based custom evaluators (sandbox: numpy, pandas, sklearn, nltk; no network; 256KB limit) |
| **Custom `@target` classes** (`type: custom`) | ✅ Any Python code | ❌ Not supported — use `azure_ai_model` target instead |
| **Foundry-deployed models** (`type: azure_ai_model`) | ✅ Via connections config | ✅ As `azure_ai_model` target |
| **Foundry agents** (`type: azure_ai_agent`) | ❌ Out of scope | ❌ Out of scope — needs unified approach for tool calls, structured output, conversation history |
| **Cartesian product** (multi-variant) | ✅ | ✅ 1 eval, N runs (one per variant for comparison) |
| **Progress bar** | ✅ Per-record Rich progress | ✅ Polling status updates |
| **Result persistence** | Local JSONL + JSON | Foundry Evaluations portal |

### Remote compute sandbox limits (code-based custom metrics)

- **Code size**: < 256 KB
- **Execution**: 2 min timeout per item
- **No network access** at runtime
- **Memory**: 2 GB, **Disk**: 1 GB, **CPU**: 2 cores
- **Available packages**: numpy, scipy, pandas, scikit-learn, rapidfuzz, sympy, jsonschema, pydantic, deepdiff, nltk, rouge-score, pyyaml
- **NLTK corpora**: punkt, stopwords, wordnet, omw-1.4, names (preloaded)

### Recommended patterns

| Goal | Approach |
|------|----------|
| Iterate quickly on local data | `local-evals run -c evals.yaml --no-tracking` |
| Run locally, share results in Foundry | `local-evals run -c evals_tracking.yaml` (tracking_backend: foundry) |
| Evaluate at scale in the cloud | `local-evals run -c evals_remote.yaml --remote` |
| Test a Foundry-deployed model | `local-evals run -c evals_remote_model.yaml --remote` (with target) |
| Use custom Python metrics | Run locally + tracking (full Python flexibility) |
| Compare prompt strategies | Cartesian locally + tracking: `demo/prompt_comparison_tracking.yaml` |
| Compare variants remotely | Remote cartesian: `demo/evals_remote_cartesian.yaml --remote` |

---

## CLI Commands


```
local-evals run          # Run evaluation (--remote for cloud, --no-tracking to skip)
local-evals new <name>   # Scaffold a new evaluation project
local-evals validate     # Validate config file
local-evals list         # List built-in evaluators
local-evals view         # View past results
local-evals clear        # Clean experiment output
local-evals compute      # Show compute backend config
local-evals tracking     # Show tracking backend config
```

## Key YAML Sections

| Section | Purpose | Example |
|---------|---------|---------|
| `compute` | Where evaluation **runs** | `type: "foundry"` + `azure_ai_project` |
| `tracking_backend` | Where results are **published** | `type: "foundry"` + `azure_ai_project` |
| `connections` | Azure OpenAI endpoint for LLM-based metrics | `azure_endpoint` + `azure_deployment` |
| `targets` | What to evaluate. Optional for dataset-only scoring | `type: "azure_ai_model"` + `deployment_name` (str or list) |
| `targets.connection_name` | Which connection for **local** execution (ignored with `--remote`) | `"default"` |
| `metrics` | Which evaluators to run + field mapping | `name: "f1_score"` + `mapping` |
| `dataset` | Input data (JSONL/CSV) | `type: "jsonl"` + `data_path` |
