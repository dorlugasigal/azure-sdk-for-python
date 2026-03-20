export interface VoiceoverSegment {
  startFrame: number;
  endFrame: number;
  text: string;
}

export const VOICEOVER_SEGMENTS: VoiceoverSegment[] = [
  // Title (0-143) — audio: 01-title.mp3 (4.4s)
  { startFrame: 5, endFrame: 140, text: "Let's evaluate a question-answering dataset using the local-evals CLI." },

  // YAML Config (143-1043) — audio: 02-config.mp3 (20.3s) + 03-metric.mp3 at +630 (8.7s)
  { startFrame: 145, endFrame: 380, text: "Our YAML config defines the experiment. Two models — GPT-4.1-mini and GPT-4.1." },
  { startFrame: 380, endFrame: 540, text: "Each at temperatures 0.3 and 0.9, giving four variants." },
  { startFrame: 540, endFrame: 620, text: "The dataset is JSONL." },
  { startFrame: 620, endFrame: 770, text: "For metrics: relevance and coherence are built-in, plus our custom conciseness." },
  { startFrame: 773, endFrame: 1040, text: "The conciseness metric is a grade function that scores response length — highest scores for 50 to 200 characters." },

  // Local Run + View (1043-1608) — audio: 04-local.mp3 (14.9s)
  { startFrame: 1045, endFrame: 1200, text: "Now we run locally with a small dataset. The CLI evaluates all four variants with our three metrics." },
  { startFrame: 1200, endFrame: 1490, text: "In the browser we can see the metrics, compare aggregated results across models, and view evaluation results per row." },

  // Remote + Dashboard (1608-2785) — audio: 06-remote.mp3 (33s)
  { startFrame: 1610, endFrame: 1810, text: "Now we add the remote flag. The CLI converts from the local evaluator engine into the equivalent cloud SDK code." },
  { startFrame: 1810, endFrame: 2010, text: "It uploads the dataset to Azure AI Foundry, and creates an evaluation with evaluation runs beneath it." },
  { startFrame: 2010, endFrame: 2200, text: "Here we can see that our custom conciseness metric was automatically uploaded to the evaluator catalog." },
  { startFrame: 2200, endFrame: 2380, text: "Meanwhile the CLI is polling for job statuses, waiting for each run to complete." },
  { startFrame: 2380, endFrame: 2650, text: "We can see the detailed metrics for each row, and our custom conciseness score right alongside the built-in evaluators." },

  // Outro (2785-2845) — silent black
];
