# local-evals Demo

## Architecture

![local-evals Architecture](docs/local-evals-architecture.drawio.png)

> 📐 Editable source: [local-evals-architecture.drawio](docs/local-evals-architecture.drawio)

local-evals separates **what** to evaluate (config) from **how** to run it (CLI flags):

- **Config** defines: dataset, targets, evaluators, connections
- **CLI flags** control: `--remote` (Foundry cloud) and `--no-tracking` (skip result publishing)

```bash
# Same config, different modes:
local-evals run -c config.yaml --no-tracking     # Local only, skip publishing
local-evals run -c config.yaml                    # Local + publish to Foundry (tracking_backend in config)
local-evals run -c config.yaml --remote           # Run on Foundry cloud
```

---

## Demos

### 1. Dataset Evaluation — NLP + LLM-as-judge

Score pre-computed responses with built-in metrics. No targets needed.

```bash
# Local only (F1 is local, relevance calls Azure OpenAI)
local-evals run -c demo/configs/evals_mixed.yaml --no-tracking

# Same config, publish results to Foundry
local-evals run -c demo/configs/evals_mixed.yaml

# Same config, run entirely on Foundry cloud
local-evals run -c demo/configs/evals_mixed.yaml --remote
```

**Config:** [`configs/evals_mixed.yaml`](configs/evals_mixed.yaml) — `f1_score` (NLP) + `relevance` (LLM-as-judge) on a QA dataset.

---

### 2. Custom Evaluator

Create your own `@evaluator` class — auto-discovered from the working directory.

```bash
local-evals run -c demo/configs/evals_custom_evaluator.yaml --no-tracking
```

**Config:** [`configs/evals_custom_evaluator.yaml`](configs/evals_custom_evaluator.yaml) — `f1_score` + custom `answer_length` from [`evaluators/answer_length_evaluator.py`](evaluators/answer_length_evaluator.py).

---

### 3. Model Comparison — Cartesian Product

Compare **multiple models × multiple parameters** in one experiment.

```bash
# Run locally
local-evals run -c demo/configs/evals_model_comparison.yaml --no-tracking

# Run on Foundry cloud (side-by-side comparison in portal)
local-evals run -c demo/configs/evals_model_comparison.yaml --remote
```

**Config:** [`configs/evals_model_comparison.yaml`](configs/evals_model_comparison.yaml) — 2 models × 2 temperatures = 4 evaluations with `relevance` + `coherence`.

---

### 4. Agent Evaluation — Tools + OTel Tracing

Evaluate an AI agent with **tool calls**. Targets just return `{"answer": text}` — the engine auto-captures tool calls, messages, and token usage via OTel tracing.

```bash
# Full agent eval (coherence, task adherence, tool call accuracy)
local-evals run -c demo/configs/evals_agent_full.yaml --no-tracking

# Same, publish results to Foundry
local-evals run -c demo/configs/evals_agent_full.yaml
```

**Config:** [`configs/evals_agent_full.yaml`](configs/evals_agent_full.yaml) — MAF weather agent with `coherence`, `response_completeness`, `task_adherence`, `intent_resolution`, `tool_call_accuracy`.

**Target:** [`targets/weather_agent_target.py`](targets/weather_agent_target.py) — the `infer()` method is just:
```python
def infer(self, input):
    result = await self._agent.run(query)
    return {"answer": result.text}  # Engine auto-enriches from OTel traces
```

---

### 5. Multi-Framework Agent Comparison

Same weather agent, 3 frameworks, side-by-side:

```bash
local-evals run -c demo/configs/evals_multi_framework.yaml --no-tracking
```

**Config:** [`configs/evals_multi_framework.yaml`](configs/evals_multi_framework.yaml)

| Framework | Target | `infer()` returns |
|-----------|--------|-------------------|
| **MAF** | [`targets/weather_agent_target.py`](targets/weather_agent_target.py) | `{"answer": result.text}` |
| **OpenAI SDK** | [`targets/openai_agent_target.py`](targets/openai_agent_target.py) | `{"answer": response.output_text}` |
| **LangChain** | [`targets/langchain_agent_target.py`](targets/langchain_agent_target.py) | `{"answer": response.content}` |

All return just the answer — the engine auto-enriches with `output_items`, `tool_calls`, `tool_definitions` from OTel traces.

---

## Quick Reference

### CLI

```bash
local-evals run -c <config>                        # Run locally + publish (if tracking configured)
local-evals run -c <config> --no-tracking          # Run locally, skip publishing
local-evals run -c <config> --remote               # Run on Foundry cloud
local-evals list                                   # List built-in evaluators
local-evals new <name>                             # Scaffold new project
```

### Config Structure

Configs describe **what** to evaluate — never how to run it:

```yaml
experiment:
  name: "my-eval"
  dataset:                    # Input data
    type: "jsonl"
    args: { data_path: "data.jsonl" }
  targets:                    # What to evaluate (optional)
    - name: "my_agent"
      type: "custom"          # or "azure_ai_model"
  evaluators:                 # Which metrics to compute
    - name: "relevance"
      mapping:
        query: "dataset.question"
        response: "model.answer"
  connections:                # Azure OpenAI for LLM-as-judge evaluators
    default:
      azure_endpoint: "..."
      azure_deployment: "gpt-4.1-mini"
```

### Capabilities

| Feature | Local | Remote (Foundry) |
|---------|-------|-------------------|
| Built-in metrics | ✅ | ✅ |
| Custom `@evaluator` | ✅ Full Python | ⚠️ Sandbox |
| Custom `@target` | ✅ | ❌ Use `azure_ai_model` |
| OTel trace capture | ✅ Auto-enabled | N/A |
| Cartesian product | ✅ | ✅ |

### Directory Structure

```
demo/
├── configs/              # What to evaluate
│   ├── evals_mixed.yaml              # Dataset: F1 + relevance
│   ├── evals_custom_evaluator.yaml   # Dataset: custom @evaluator
│   ├── evals_model_comparison.yaml   # Models: 2 models × 2 temps
│   ├── evals_agent_full.yaml         # Agent: tools + tracing
│   └── evals_multi_framework.yaml    # Agent: MAF vs OpenAI vs LangChain
├── data/                 # Datasets
│   ├── data.jsonl
│   ├── data_small.jsonl
│   └── agent_eval_data.jsonl
├── targets/              # Agent @target implementations
│   ├── weather_agent_target.py       # MAF
│   ├── openai_agent_target.py        # OpenAI SDK
│   └── langchain_agent_target.py     # LangChain
├── evaluators/           # Custom @evaluator implementations
│   ├── answer_length_evaluator.py
│   └── response_completeness_evaluator.py
└── docs/                 # Diagrams & walkthrough
```
