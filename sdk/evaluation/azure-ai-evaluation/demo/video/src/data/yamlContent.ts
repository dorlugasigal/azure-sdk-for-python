export const YAML_CONFIG = `experiment:
  name: "model-comparison"

  compute:
    type: "foundry"
    azure_ai_project: "https://foundry-evee.services.ai.azure.com/..."

  targets:
    - name: "model_compare"
      type: "azure_ai_model"
      deployment_name: ["gpt-4.1-mini", "gpt-4.1"]
      connection_name: "default"
      args:
        - temperature: [0.3, 0.9]

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
    - name: "conciseness"
      mapping:
        response: "model.answer"

  connections:
    default:
      azure_endpoint: "https://foundry-evee.cognitiveservices.azure.com/"
      azure_deployment: "gpt-4.1-mini"`;

export const CUSTOM_METRIC_CODE = `def grade(sample: dict, item: dict) -> float:
    """Score response conciseness.
    Prefers 50-200 character answers.
    Returns a single float 0.0 to 1.0.
    """
    response = item.get("response", "")
    if not response:
        return 0.0
    length = len(response)
    if length < 50:
        return 0.5
    elif length <= 200:
        return 1.0
    else:
        return max(0.3, round(
            1.0 - (length - 200) / 500, 3
        ))`;

// Highlight annotations for the YAML config scene (local frames, 0 = scene start, 900 frames total)
// Config audio: 0-609, Metric audio: 630-890
export const YAML_ANNOTATIONS = [
  { lineRange: [10, 11] as [number, number], label: "2 models: gpt-4.1-mini & gpt-4.1", color: "#58a6ff", startFrame: 10, endFrame: 250 },
  { lineRange: [13, 14] as [number, number], label: "2 temperatures: 0.3 & 0.9 → 4 variants", color: "#bc8cff", startFrame: 250, endFrame: 400 },
  { lineRange: [16, 20] as [number, number], label: "QA dataset (JSONL)", color: "#3fb950", startFrame: 400, endFrame: 480 },
  { lineRange: [22, 29] as [number, number], label: "Built-in metrics", color: "#d29922", startFrame: 480, endFrame: 560 },
  { lineRange: [30, 32] as [number, number], label: "Custom metric", color: "#f85149", startFrame: 560, endFrame: 895 },
];
