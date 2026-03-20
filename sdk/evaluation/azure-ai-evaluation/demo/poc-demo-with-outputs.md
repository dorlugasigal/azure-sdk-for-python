# Azure AI Evaluation SDK v2.0 — POC

We added the evee evaluation engine (`_engine/`) into the real `azure-ai-evaluation` SDK, decorated the existing evaluators (`RelevanceEvaluator`, `F1ScoreEvaluator`) with evee's `@metric` so they auto-register in the engine's metric registry, and built a unified `evaluate_v2()` function that routes everything through the engine — whether called from Python, YAML config, or CLI — with `azure_ai_project` automatically connecting to Foundry via `AIProjectClient` to run the same evaluators against cloud models (GPT-4.1-mini).

> Real SDK evaluators decorated with `@metric`, running through the evee engine. Local or cloud via `azure_ai_project`.

```python
import os, json

if os.path.basename(os.getcwd()) == "demo":
    os.chdir("..")

from azure.ai.evaluation._eval_v2 import evaluate_v2
from azure.ai.evaluation import RelevanceEvaluator, F1ScoreEvaluator

DATA = "demo/data.jsonl"
PROJECT = "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/api/projects/foundry-project-evee-ko9z2s7c"

print("Ready")

```

    Ready

## How It Works

The real SDK evaluators (`RelevanceEvaluator`, `F1ScoreEvaluator`) are decorated with `@metric` at the bottom of their source files. This registers them in the evee engine's metric registry — making them discoverable from YAML config and runnable through the engine's parallel execution pipeline.

```python
# Added to _evaluators/_f1_score/_f1_score.py:
@_evee_metric(name='f1_score')
class _F1ScoreEveeMetric(_EveeBaseMetric):
    def __init__(self, connections_registry=None, context=None, **kwargs):
        self._evaluator = F1ScoreEvaluator()

    def compute(self, response='', ground_truth='', **kwargs):
        return self._evaluator(response=response, ground_truth=ground_truth)

    def aggregate(self, scores):
        vals = [s.get('f1_score', 0) for s in scores]
        return {'f1_score_mean': sum(vals) / len(vals)}
```

When the engine encounters `name: "relevance"` in the YAML config, it looks up the registry, finds the decorated evaluator, and if a cloud connection is configured, the evaluator automatically uses the Foundry model.

## 1. Local Evaluation — No Model Needed

F1 is a deterministic NLP metric from the real SDK. Runs instantly, offline, no API key.

```python
result_local = evaluate_v2(
    data=DATA,
    evaluators={"f1": F1ScoreEvaluator},
    evaluator_config={"f1": {"column_mapping": {
        "response": "${data.answer}",
        "ground_truth": "${data.context}",
    }}},
)

```

    Status: completed  Records: 10
      f1_score_mean=0.2545
      f1: ?

## 2. Cloud Evaluation — via `azure_ai_project`

Same call — add `azure_ai_project`. The function connects to the Foundry project via `AIProjectClient`, discovers the deployed model (GPT-4.1-mini), and injects the connection into the engine. The `@metric`-decorated `RelevanceEvaluator` picks up the connection and calls the real LLM-as-judge.

```python
result_cloud = evaluate_v2(
    data=DATA,
    evaluators={"relevance": RelevanceEvaluator},
    evaluator_config={"relevance": {"column_mapping": {
        "query": "${data.question}",
        "response": "${data.answer}",
    }}},
    azure_ai_project=PROJECT,
)

```

      Connected to project, using model: gpt-4.1-mini

    Status: completed  Records: 10
      relevance_mean=4.2
      relevance: 5.0  model=gpt-4.1-mini-2025-04-14
        reason: The response directly and accurately defines prompt engineering, clearly addressing the user's query

## 3. Local + Cloud Together

F1 (local, instant) + Relevance (cloud, GPT-4.1-mini judge) — one call, both through the engine.

```python
result_both = evaluate_v2(
    data=DATA,
    evaluators={"relevance": RelevanceEvaluator, "f1": F1ScoreEvaluator},
    evaluator_config={
        "relevance": {"column_mapping": {"query": "${data.question}", "response": "${data.answer}"}},
        "f1": {"column_mapping": {"response": "${data.answer}", "ground_truth": "${data.context}"}},
    },
    azure_ai_project=PROJECT,
)

```

      Connected to project, using model: gpt-4.1-mini

    Status: completed  Records: 10
      relevance_mean=4.2
      f1_score_mean=0.2545
      relevance: 4.0  model=gpt-4.1-mini-2025-04-14
        reason: The response directly addresses the user's question by recommending a specific SDK for evaluating AI

## 4. Config-Driven via YAML

No Python needed. The YAML references the registered metric names, the engine creates the evaluators, and connections provide the model endpoint.

```python
with open("demo/evals.yaml") as f:
    print(f.read())

```

    experiment:
      name: "cloud-eval-demo"
    
      models:
        - name: "default"
          args:
            temperature: [0.7]
    
      dataset:
        name: "qa_data"
        type: "jsonl"
        args:
          data_path: "demo/data.jsonl"
    
      metrics:
        - name: "relevance"
          mapping:
            query: "dataset.question"
            response: "dataset.answer"
            context: "dataset.context"
    
      connections:
        default:
          azure_endpoint: "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/"
          azure_deployment: "gpt-4.1-mini"
    

```python
result_config = evaluate_v2(config="demo/evals.yaml")

```

    Status: completed  Records: 10
      relevance_mean=4.2
      relevance: 5.0  model=gpt-4.1-mini-2025-04-14
        reason: The response directly and accurately defines prompt engineering, clearly addressing the user's query

### Output Files

The engine persists per-record JSONL + summary JSON — structured, reproducible, uploadable to Foundry.

```python
# Re-run to show output files (previous _show cleaned up)
result_files = evaluate_v2(config="demo/evals.yaml")
from pathlib import Path
output_dir = Path(result_files["output_path"])

print("Output files:")
for f in sorted(output_dir.iterdir()):
    print(f"  {f.name:<45} {f.stat().st_size:>6} bytes")

import shutil; shutil.rmtree(output_dir.parent.parent, ignore_errors=True)

```

    Output files:
      default__temperature=0.7_results.jsonl         18364 bytes
      default__temperature=0.7_summary.json            148 bytes

## 5. CLI

```python
import subprocess

proc = subprocess.run(
    ["python", "-m", "azure.ai.evaluation.cli", "run", "-c", "demo/evals.yaml"],
    capture_output=True, text=True,
)
print(proc.stdout)

```

    Running evaluation from demo/evals.yaml...
    
      Status:    completed
      Records:   10
      Variants:  1
      Output:    experiment/output/cloud-eval-demo_v1.0__2026-03-17_00-11-34
    

## 6. Prompt Strategy Comparison — Real API Calls

A common evaluation task: **which prompt strategy produces better answers?**

We define a `@model` class that calls GPT-4.1-mini with three different system prompts:

| Strategy | System Prompt | What It Tests |
|----------|--------------|---------------|
| **baseline** | "Answer concisely" | Raw model quality with no guidance |
| **single_shot** | 1 example Q&A, then the question | Does one example improve quality? |
| **few_shot** | 3 example Q&As, then the question | Do more examples help further? |

The engine auto-discovers the `@model(name="prompt_compare")` from `demo/prompt_models.py`, expands the parameter grid (3 strategies × 10 questions = 30 API calls), and scores each answer with RelevanceEvaluator + F1.

```python
# Show the @model class
with open("demo/prompt_models.py") as f:
    print(f.read())

```

    """@model classes for prompt strategy comparison.
    
    Calls GPT-4.1-mini via Foundry with different prompt strategies:
    - baseline: just answer the question
    - single_shot: one example shown
    - few_shot: multiple examples shown
    """
    from __future__ import annotations
    from typing import Any, Dict
    from azure.ai.evaluation._engine.decorators import model, BaseModel
    
    
    SYSTEM_PROMPTS = {
        "baseline": "Answer the question concisely and accurately.",
        "single_shot": """Answer the question concisely and accurately.
    
    Example:
    Q: What is Python?
    A: Python is a high-level, interpreted programming language known for its readability and versatility, widely used in web development, data science, and automation.""",
        "few_shot": """Answer the question concisely and accurately.
    
    Example 1:
    Q: What is Python?
    A: Python is a high-level, interpreted programming language known for its readability and versatility, widely used in web development, data science, and automation.
    
    Example 2:
    Q: What is Docker?
    A: Docker is a platform for building, shipping, and running applications in lightweight, isolated containers that package code with all its dependencies.
    
    Example 3:
    Q: What is REST?
    A: REST (Representational State Transfer) is an architectural style for designing networked applications using stateless HTTP requests to access and manipulate resources.""",
    }
    
    
    @model(name="prompt_compare")
    class PromptCompareModel(BaseModel):
        """Calls GPT-4.1-mini with configurable prompt strategy."""
    
        def __init__(self, prompt: str = "baseline", temperature: float = 0.7,
                     max_tokens: int = 200, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.prompt_strategy = prompt
            self.temperature = temperature
            self.max_tokens = max_tokens
            self.system_prompt = SYSTEM_PROMPTS.get(prompt, SYSTEM_PROMPTS["baseline"])
    
            # Create Azure OpenAI client
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            from openai import AzureOpenAI
            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            )
            self._client = AzureOpenAI(
                azure_endpoint="https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/",
                azure_ad_token_provider=token_provider,
                api_version="2024-10-21",
            )
    
        def infer(self, input: Dict[str, Any]) -> Dict[str, Any]:
            question = input.get("question", "")
            response = self._client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": question},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return {"answer": response.choices[0].message.content}
    

```python
# Show the comparison config
with open("demo/prompt_comparison.yaml") as f:
    print(f.read())

```

    experiment:
      name: "prompt-strategy-comparison"
    
      models:
        - name: "prompt_compare"
          args:
            - prompt: ["baseline", "single_shot", "few_shot"]
            - temperature: [0.7]
            - max_tokens: [200]
    
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
            context: "dataset.context"
        - name: "f1_score"
          mapping:
            response: "model.answer"
            ground_truth: "dataset.context"
    
      connections:
        default:
          azure_endpoint: "https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/"
          azure_deployment: "gpt-4.1-mini"
    

```python
# Engine auto-discovers @model from demo/prompt_models.py — no import needed
result_compare = evaluate_v2(config="demo/prompt_comparison.yaml")

print(f"Variants: {result_compare['models_evaluated']}  Records: {result_compare['total_records']}")

```

    Variants: 3  Records: 30
    Status: completed  Records: 30
    
    Variant                                                 Metrics
    --------------------------------------------------------------------------------
      max_tokens=200_prompt=baseline_temperature=0.7        relevance_mean=4.4, f1_score_mean=0.175
      max_tokens=200_prompt=few_shot_temperature=0.7        relevance_mean=4.4, f1_score_mean=0.2392
      max_tokens=200_prompt=single_shot_temperature=0.7     relevance_mean=4.5, f1_score_mean=0.1983
      relevance: 4.0  model=gpt-4.1-mini-2025-04-14
        reason: The response directly and clearly defines prompt engineering, explaining its purpose and key aspects

## Summary

| Mode | Code | What Happens |
|------|------|-------------|
| **Local** | `evaluate_v2(data=..., evaluators={"f1": F1ScoreEvaluator})` | Engine runs `@metric`-decorated evaluator locally |
| **Cloud** | `evaluate_v2(..., azure_ai_project=PROJECT)` | Connects via `AIProjectClient`, injects model, engine runs `@metric` with cloud model |
| **Config** | `evaluate_v2(config="evals.yaml")` | YAML defines metrics + connections, engine does everything |
| **CLI** | `python -m azure.ai.evaluation.cli run -c evals.yaml` | Same engine, from terminal |

**No bypass. No bridge. Real SDK evaluators decorated with `@metric`, running through the evee engine.**

