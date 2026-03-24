# OTel-Based Agent Evaluation — Technical Findings

## How It Works

Our evaluation engine transparently captures agent execution data via OpenTelemetry. The user writes their agent target and returns just `{"answer": text}`. The engine automatically:

1. Sets up OTel providers (TracerProvider + LoggerProvider)
2. Enables framework-specific instrumentation
3. Wraps each `target.infer()` call in a parent span
4. Collects all child spans and log events
5. Builds structured `output_items`, `tool_calls`, `tool_definitions` from the traces
6. Feeds them to evaluators (task_adherence, tool_call_accuracy, etc.)
7. Emits `gen_ai.evaluation.result` events back to the traces

Zero manual plumbing. The target code is 100% unchanged.

---

## Framework Coverage

| Capability | LangChain | OpenAI Responses API | MAF |
|---|---|---|---|
| **How OTel works** | Via OpenAI SDK underneath — the OTel instrumentor hooks `chat.completions.create`. LangChain has native OTel (`LANGSMITH_OTEL_ENABLED`) but it requires LangSmith auth. | ❌ Not yet instrumented | Native — `agent_framework.observability` emits OTel directly |
| **LLM call spans** | ✅ Native + via OpenAI instrumentor | ❌ | ✅ Native spans |
| **Input/output messages** | ✅ Span attributes + log events | ❌ | ✅ Span attributes (`gen_ai.input/output.messages`) |
| **Tool calls** | ✅ In log events + native `execute_tool` spans | ❌ | ✅ Dedicated `execute_tool` spans with `gen_ai.tool.call.*` |
| **Tool definitions** | ❌ | ❌ | ✅ `gen_ai.tool.definitions` on `invoke_agent` span |
| **Token usage** | ✅ | ❌ | ✅ |
| **Agent identity** | ❌ | ❌ | ✅ `gen_ai.agent.id`, `gen_ai.agent.name` |
| **Standard semconv** | ✅ `gen_ai.*` attributes | N/A | ✅ Full `gen_ai.*` compliance |

### Key Insight

**MAF is the most OTel-complete framework.** It emits all GenAI semantic convention attributes natively — including `gen_ai.tool.definitions` which no other framework/instrumentor supports yet. You just call `enable_instrumentation(enable_sensitive_data=True)` and it emits everything to the global OTel providers.

**LangChain works via the OpenAI instrumentor** — it calls `openai.chat.completions.create()` internally, which the OTel instrumentor intercepts. LangChain has a native OTel mode (`LANGSMITH_OTEL_ENABLED=true`) that adds chain/tool spans, but it requires `LANGSMITH_TRACING=true` which phones home to LangSmith servers and spams auth errors without credentials. We use the OpenAI instrumentor path only.

**OpenAI Responses API is the gap** — `responses.create()` is a different method that the instrumentor doesn't hook yet.

---

## What's Coming (Active PRs)

### 1. OpenAI Responses API Instrumentation
- **PR:** [open-telemetry/opentelemetry-python-contrib#4337](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4337)
- **Title:** "feat(genai-openai): OpenAI responses extractors"
- **Status:** Open, assigned to lmolkova (Microsoft), updated March 24, 2026
- **Impact:** When merged, `responses.create()` will be instrumented — OpenAI Agents SDK targets will work fully via OTel

### 2. Tool Definitions JSON Schema
- **PR:** [open-telemetry/semantic-conventions#3378](https://github.com/open-telemetry/semantic-conventions/pull/3378)
- **Title:** "Add JSON Schema Definition for gen_ai.tool.definitions"
- **Status:** Open, actively reviewed, updated March 23, 2026
- **Impact:** Once the schema is standardized and instrumentors implement it, LangChain and OpenAI targets won't need to return `tool_definitions` at all — the engine will extract them from OTel traces automatically

---

## What This Means for Agent Evaluation

### Today
- **MAF agents:** Full OTel coverage. Target returns `{"answer": text}`, engine gets everything from traces. All evaluators work.
- **LangChain agents:** Good OTel coverage (messages, tool calls, tokens). Missing tool_definitions only.
- **OpenAI Agents SDK:** No OTel coverage yet. Evaluators only get the final answer text. Waiting on PR #4337.

### After PRs Merge
- **All 3 frameworks:** Full OTel coverage. Targets return `{"answer": text}`. Engine extracts everything from traces. All evaluators work with zero manual plumbing.

### The Pattern
```python
@target(name="my_agent")
class MyAgent(BaseTarget):
    def infer(self, input):
        # Any framework — MAF, LangChain, OpenAI, custom
        result = run_my_agent(input["query"])
        return {"answer": result}
        # That's it. Engine handles everything else via OTel.
```

---

## OTel Data Flow

```
Agent target returns {"answer": text}
         │
         ▼
Engine wraps infer() in OTel parent span
         │
         ├─── MAF: enable_instrumentation() → emits spans + attributes
         ├─── LangChain: OpenAIInstrumentor → hooks underlying chat.completions.create
         └─── OpenAI SDK: (waiting on PR #4337 for responses.create)
         │
         ▼
Collected spans + log events (same trace_id)
         │
         ├── gen_ai.output.messages → output_items (conversation format)
         ├── gen_ai.tool.call.* → tool_calls
         ├── gen_ai.tool.definitions → tool_definitions
         └── gen_ai.usage.* → token counts
         │
         ▼
Auto-enriched into model output
         │
         ├── Evaluator: task_adherence(query, response=output_items)
         ├── Evaluator: tool_call_accuracy(query, response=output_items, tool_definitions)
         ├── Evaluator: coherence(query, response=answer)
         └── Evaluator: intent_resolution(query, response=output_items)
         │
         ▼
gen_ai.evaluation.result events emitted back to traces
         │
         ▼
Correlated in Azure Monitor / App Insights
```
