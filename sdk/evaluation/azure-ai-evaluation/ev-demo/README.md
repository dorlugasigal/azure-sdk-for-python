# ev-demo — Azure AI Evaluation Engine Demos

Demonstrations of the `ev` evaluation CLI for assessing AI models and agents.

## Quick Start

```bash
# Install dependencies
uv sync

# Run the quickstart evaluation (no Azure required)
ev run
```

## Demos

### 1. Multi-Model Comparison with System Prompt Variants

Compares GPT-4.1-mini vs GPT-4.1 across different system prompts and temperature settings using Cartesian product expansion.

**Creates 8 variants:** 2 models × 2 system prompts × 2 temperatures

```bash
ev run -c configs/demo_model_comparison.yaml
```

**What it demonstrates:**
- `cloud` config block for Azure OpenAI settings
- `deployment_name` list for model comparison
- `system_prompt` variants in `args` for prompt engineering experiments
- Per-evaluator `deployment_name` override
- Built-in evaluators: relevance, coherence, f1_score
- Custom evaluator: conciseness

### 2. Azure AI Agent Evaluation

Evaluates a deployed Foundry agent with built-in + custom evaluators.

> **Prerequisites:** This demo requires a deployed agent on Azure AI Foundry.
> Set `AZURE_AGENT_NAME` in `.env` to your agent's name.

```bash
ev run -c configs/demo_agent_eval.yaml
```

**What it demonstrates:**
- `type: "azure_ai_agent"` target configuration
- Agent-specific evaluators: task_adherence, tool_call_accuracy
- Custom evaluator: response_completeness
- Per-evaluator deployment override (`relevance` uses gpt-4.1)

### 3. Multi-Framework Agent Comparison

Compares weather agents built with Microsoft Agent Framework, OpenAI, and LangChain side-by-side.

> **Prerequisites:** Requires Azure OpenAI credentials and the framework-specific
> dependencies installed (`agent-framework`, `langchain`, etc.).

```bash
ev run -c configs/demo_multi_framework.yaml
```

**What it demonstrates:**
- Custom `@target` agents with different frameworks
- Agent trace capture (OTel) for tool call analysis
- Tool-focused evaluators: tool_selection, tool_call_accuracy
- Framework-agnostic evaluation

## Configuration Reference

### Target Types

The engine supports three target types:

| Type | Description | Variants | Requires Azure |
|------|-------------|----------|----------------|
| `custom` | Your own `@target` class | Via `args` | No |
| `azure_ai_model` | Azure OpenAI chat completion | Via `deployment_name`, `args` | Yes |
| `azure_ai_agent` | Deployed Foundry agent | None (single) | Yes |

### Target Variants (Cartesian Product)

Any parameter in `args` can be a list — the engine creates all combinations automatically:

```yaml
targets:
  - name: "qa_model"
    type: "azure_ai_model"
    deployment_name: ["gpt-4.1-mini", "gpt-4.1"]   # 2 models
    args:
      - system_prompt:                                # 2 prompts
          - "Answer concisely in one sentence."
          - "Provide detailed answers with examples."
        temperature: [0.3, 0.9]                       # 2 temperatures
```

**Result:** 2 × 2 × 2 = **8 variants**, each evaluated independently.

#### What you can vary on `azure_ai_model`:

| Parameter | Example | Effect |
|-----------|---------|--------|
| `deployment_name` | `["gpt-4.1-mini", "gpt-4.1"]` | Compare different models |
| `system_prompt` | `["Be concise.", "Be thorough."]` | Compare prompt strategies |
| `temperature` | `[0.3, 0.7, 0.9]` | Sampling temperature |
| `top_p` | `[0.8, 1.0]` | Nucleus sampling |
| `max_tokens` | `[100, 500]` | Response length limit |
| `max_completion_tokens` | `[100, 500]` | Completion token limit |
| `frequency_penalty` | `[0.0, 0.5]` | Repetition penalty |
| `presence_penalty` | `[0.0, 0.5]` | Topic diversity |
| `seed` | `[42]` | Reproducibility |

#### What you can vary on `custom` targets:

Any key-value pair — your `@target` class receives them via `config` dict:

```yaml
targets:
  - name: "my_agent"
    args:
      - strategy: ["chain_of_thought", "react", "direct"]
        max_retries: [1, 3]
```

Your target reads them in `__init__`:
```python
@target(name="my_agent")
class MyAgent(BaseTarget):
    def __init__(self, config=None, context=None):
        super().__init__(context)
        self.strategy = config.get("strategy", "direct")
        self.max_retries = config.get("max_retries", 1)
```

#### `azure_ai_agent` targets:

Agent targets do NOT support variants — each agent config produces exactly one target:

```yaml
targets:
  - name: "my-agent"
    type: "azure_ai_agent"
    agent_name: "weather-agent"           # Agent name in Foundry
    # agent_version: "1.0"               # Optional version (default: latest)
    # instructions: "Override prompt"     # Optional instruction override
```

#### Target Input Mapping

When dataset field names don't match what your target's `infer()` method expects, use
`input_mapping` to rename fields before inference:

```yaml
targets:
  - name: "my_agent"
    input_mapping:
      query: "dataset.user_message"       # infer() receives query=<dataset["user_message"]>
      context: "dataset.background_info"  # infer() receives context=<dataset["background_info"]>
```

This is only needed when field names differ — by default the engine auto-detects
common query fields (`query`, `question`, `prompt`, `input`).

### Cloud Block
```yaml
cloud:
  foundry_endpoint: "${AZURE_OPENAI_ENDPOINT}"   # Must end with /openai/v1
  foundry_project: "${AZURE_AI_PROJECT}"          # For remote compute
  default_evaluator_deployment: "gpt-4.1-mini"    # Default LLM for evaluators
  app_insights: "${AZURE_APP_INSIGHTS_CONNECTION_STRING}"  # Optional
```

Run `ev cloud set` to configure interactively with Azure resource discovery.

### Per-Evaluator Deployment Override

Each evaluator can use a different model than the default:

```yaml
evaluators:
  - name: "relevance"
    deployment_name: "gpt-4.1"    # Uses gpt-4.1 instead of default gpt-4.1-mini
    mapping:
      query: "dataset.question"
      response: "target.response"
```

### Evaluator Mapping

Maps evaluator inputs to dataset or target output fields:

```yaml
mapping:
  query: "dataset.question"      # Read from dataset record
  response: "target.response"    # Read from target output
  ground_truth: "dataset.ground_truth"  # For reference-based metrics
```

- `dataset.<field>` — value from the dataset record
- `target.<field>` — value from the target's `infer()` output dict

### Custom Connections

For custom evaluators that need external service access:

```yaml
connections:
  my_service:
    endpoint: "${MY_SERVICE_ENDPOINT}"
    api_key: "${MY_SERVICE_KEY}"
```

Access in your evaluator via `ExecutionContext`:
```python
@evaluator(name="my_evaluator")
class MyEvaluator(BaseEvaluator):
    def __init__(self, config=None, context=None):
        super().__init__(context)
        conn = context.connections_registry["my_service"]
        self.endpoint = conn.endpoint
```

## Environment Setup

```bash
cp .env.sample .env
# Edit with your Azure credentials
```

Required for Azure demos:
- `AZURE_OPENAI_ENDPOINT` — Azure OpenAI endpoint (ending with /openai/v1)
- `AZURE_AI_PROJECT` — Foundry project endpoint
- `AZURE_OPENAI_DEPLOYMENT` — Default model deployment name

For agent demo:
- `AZURE_AGENT_NAME` — Deployed agent name in Foundry

## CLI Commands

```bash
ev run                                    # Run with default config
ev run -c configs/demo_model_comparison.yaml  # Run specific config
ev run --remote                           # Run on Foundry cloud
ev validate                               # Validate configuration
ev cloud set                              # Configure Azure (interactive)
ev view                                   # View results in browser
ev new                                    # Create new project
```
