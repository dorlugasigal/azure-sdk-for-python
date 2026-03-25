/**
 * @file Evee Results Viewer MCP App
 *
 * MLflow-like experiment comparison view with:
 * - Side-by-side comparison table of all model runs
 * - Baseline marking with delta indicators
 * - Grouping by model name
 * - Drill-down into per-record details
 */
import type { McpUiHostContext } from "@modelcontextprotocol/ext-apps";
import { useApp, useHostStyles } from "@modelcontextprotocol/ext-apps/react";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { CSSProperties } from "react";
import { StrictMode, useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { EVEE_LOGO } from "./assets/logo";
import "./global.css";

// =============================================================================
// Types
// =============================================================================

interface AggregatedEvaluators {
  number_of_records: number;
  average_response_time_ms: number;
  [key: string]: number;
}

interface ExperimentRun {
  run_id: string;
  aggregated_evaluators: AggregatedEvaluators;
  tags: Record<string, string | number>;
}

interface EvaluatorValue {
  score?: number;
  match?: boolean;
  f1_score?: number;
  precision?: number;
  recall?: number;
  explanation?: string;
  [key: string]: unknown;
}

interface ExperimentRecord {
  output: Record<string, unknown>;
  model_name: string;
  record: {
    context?: string;
    question?: string;
    ground_truth?: string;
    [key: string]: unknown;
  };
  args: Record<string, unknown>;
  run_id: string;
  evaluators: Record<string, EvaluatorValue>;
  system_evaluators: { response_time?: { response_time_ms: number } };
  model_display_name: string;
  metadata: Record<string, unknown>;
}

interface ModelData {
  model_name: string;
  model_display_name?: string;
  summary: ExperimentRun;
  records: ExperimentRecord[];
  files: {
    summary: string;
    records: string | null;
  };
}

interface ViewResultsData {
  summary: ExperimentRun;
  records: ExperimentRecord[];
  output_path: string;
  models?: ModelData[];
}

// Grouping structure for the comparison table
interface ModelGroup {
  groupName: string;
  models: ModelData[];
}

function extractResultsData(callToolResult: CallToolResult): ViewResultsData | null {
  // Find the text content block that contains valid JSON with experiment data
  const textContents = (callToolResult.content ?? []).filter((c) => c.type === "text");

  for (const content of textContents) {
    if (content.type !== "text") continue;
    try {
      const data = JSON.parse(content.text);

      if (data.summary && data.records) {
        return data as ViewResultsData;
      }

      // Legacy format: {success: true, data: {...}}
      if (data.success && data.data) {
        return data.data as ViewResultsData;
      }
    } catch {
      // Not JSON or not the right shape, try next content block
    }
  }

  return null;
}

// =============================================================================
// Styles
// =============================================================================

const styles = {
  main: {
    padding: "20px 16px",
    maxWidth: "100%",
    margin: "0 auto",
    minHeight: "100%",
    overflow: "hidden",
  } as CSSProperties,
  header: {
    marginBottom: "32px",
    paddingBottom: "20px",
  } as CSSProperties,
  headerTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: "4px",
    gap: "12px",
  } as CSSProperties,
  logoContainer: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
  } as CSSProperties,
  logo: {
    height: "32px",
    width: "auto",
    opacity: 0.9,
  } as CSSProperties,
  title: {
    fontSize: "20px",
    fontWeight: 600,
    margin: 0,
    color: "var(--color-text-primary)",
  } as CSSProperties,
  subtitle: {
    color: "var(--color-text-muted, var(--color-text-secondary))",
    fontSize: "14px",
    margin: "4px 0 0",
  } as CSSProperties,
  loading: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
    color: "var(--color-text-secondary)",
    fontSize: "14px",
  } as CSSProperties,
  error: {
    padding: "12px 16px",
    background: "var(--color-error-bg)",
    color: "var(--color-error-text)",
    borderRadius: "var(--border-radius)",
    marginBottom: "16px",
    border: "1px solid color-mix(in srgb, var(--color-error) 30%, transparent)",
    fontSize: "14px",
  } as CSSProperties,
  button: {
    padding: "8px 16px",
    borderRadius: "6px",
    border: "none",
    background: "var(--color-accent)",
    color: "#fff",
    cursor: "pointer",
    fontWeight: 500,
    fontSize: "14px",
    transition: "background 0.15s",
  } as CSSProperties,
  buttonSmall: {
    padding: "4px 10px",
    borderRadius: "4px",
    border: "1px solid var(--color-border)",
    background: "transparent",
    color: "var(--color-text-secondary)",
    cursor: "pointer",
    fontSize: "12px",
    fontWeight: 500,
    transition: "all 0.15s",
  } as CSSProperties,
  buttonSmallActive: {
    background: "var(--color-accent)",
    color: "#fff",
    borderColor: "var(--color-accent)",
  } as CSSProperties,
  // Comparison table styles
  tableWrapper: {
    overflowX: "auto" as const,
    marginBottom: "24px",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--border-radius)",
    background: "var(--color-background)",
  } as CSSProperties,
  table: {
    width: "100%",
    borderCollapse: "collapse" as const,
    fontSize: "13px",
  } as CSSProperties,
  th: {
    padding: "6px 12px",
    textAlign: "left" as const,
    borderBottom: "1px solid var(--color-border)",
    background: "#141414",
    fontWeight: 600,
    fontSize: "12px",
    whiteSpace: "nowrap" as const,
    position: "sticky" as const,
    top: 0,
    zIndex: 1,
    color: "#FFFFFF",
    fontFamily: "var(--font-sans)",
    textTransform: "lowercase" as const,
  } as CSSProperties,
  thMetricLabel: {
    padding: "6px 12px",
    textAlign: "left" as const,
    borderBottom: "1px solid var(--color-border-subtle, var(--color-border))",
    borderRight: "1px solid var(--color-border)",
    background: "var(--color-background)",
    fontWeight: 500,
    fontSize: "13px",
    whiteSpace: "nowrap" as const,
    fontFamily: "var(--font-sans)",
    minWidth: "140px",
    position: "sticky" as const,
    left: 0,
    zIndex: 1,
    color: "var(--color-text-primary)",
  } as CSSProperties,
  td: {
    padding: "6px 12px",
    borderBottom: "1px solid var(--color-border-subtle, var(--color-border))",
    textAlign: "right" as const,
    overflow: "hidden",
    textOverflow: "ellipsis" as const,
    whiteSpace: "nowrap" as const,
    maxWidth: "200px",
    fontSize: "13px",
    fontFamily: "var(--font-mono)",
  } as CSSProperties,
  groupHeader: {
    padding: "8px 16px",
    background: "var(--color-background-secondary)",
    borderBottom: "1px solid var(--color-border)",
    fontWeight: 600,
    fontSize: "11px",
    textTransform: "uppercase" as const,
    letterSpacing: "0.05em",
    color: "var(--color-text-muted, var(--color-text-secondary))",
    fontFamily: "var(--font-sans)",
  } as CSSProperties,
  sectionRow: {
    background: "var(--color-background-secondary)",
    fontWeight: 600,
    fontSize: "11px",
    textTransform: "uppercase" as const,
    letterSpacing: "0.06em",
    color: "var(--color-text-muted, var(--color-text-secondary))",
    fontFamily: "var(--font-sans)",
  } as CSSProperties,
  columnHeader: {
    padding: "10px 16px",
    textAlign: "center" as const,
    borderBottom: "1px solid var(--color-border)",
    background: "var(--color-background-secondary)",
    fontWeight: 600,
    fontSize: "13px",
    minWidth: "110px",
    maxWidth: "200px",
    overflow: "hidden",
    fontFamily: "var(--font-sans)",
    color: "var(--color-text-primary)",
  } as CSSProperties,
  baselineTag: {
    display: "inline-block",
    background: "var(--color-accent)",
    color: "#fff",
    padding: "2px 8px",
    borderRadius: "10px",
    fontSize: "10px",
    fontWeight: 600,
    marginLeft: "4px",
    verticalAlign: "middle",
    textTransform: "uppercase" as const,
    letterSpacing: "0.03em",
  } as CSSProperties,
  deltaPositive: {
    color: "var(--color-success)",
    fontSize: "11px",
    marginLeft: "6px",
    padding: "2px 6px",
    borderRadius: "4px",
    fontWeight: 600,
    whiteSpace: "nowrap" as const,
    display: "inline-block",
    background: "var(--color-success-subtle, color-mix(in srgb, var(--color-success) 12%, transparent))",
  } as CSSProperties,
  deltaNegative: {
    color: "var(--color-error)",
    fontSize: "11px",
    marginLeft: "6px",
    padding: "2px 6px",
    borderRadius: "4px",
    fontWeight: 600,
    whiteSpace: "nowrap" as const,
    display: "inline-block",
    background: "var(--color-error-bg)",
  } as CSSProperties,
  deltaNeutral: {
    color: "var(--color-text-muted, var(--color-text-secondary))",
    fontSize: "11px",
    marginLeft: "6px",
    padding: "2px 6px",
    borderRadius: "4px",
    fontWeight: 600,
    whiteSpace: "nowrap" as const,
    display: "inline-block",
    background: "color-mix(in srgb, var(--color-text-secondary) 8%, transparent)",
  } as CSSProperties,
  // Drill-down / Record detail styles
  drillDownOverlay: {
    position: "fixed" as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: "rgba(0, 0, 0, 0.6)",
    zIndex: 100,
    display: "flex",
    justifyContent: "center",
    alignItems: "flex-start",
    padding: "40px 20px",
    overflowY: "auto" as const,
    backdropFilter: "blur(4px)",
  } as CSSProperties,
  drillDownPanel: {
    background: "var(--color-background)",
    borderRadius: "12px",
    width: "100%",
    maxWidth: "960px",
    maxHeight: "calc(100vh - 80px)",
    overflowY: "auto" as const,
    boxShadow: "0 12px 48px rgba(0, 0, 0, 0.3)",
    border: "1px solid var(--color-border)",
  } as CSSProperties,
  drillDownHeader: {
    padding: "20px 24px",
    borderBottom: "1px solid var(--color-border)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    position: "sticky" as const,
    top: 0,
    background: "var(--color-background)",
    zIndex: 1,
  } as CSSProperties,
  drillDownBody: {
    padding: "20px 24px",
  } as CSSProperties,
  recordCard: {
    background: "var(--color-background-secondary)",
    borderRadius: "var(--border-radius)",
    border: "1px solid var(--color-border)",
    marginBottom: "8px",
    overflow: "hidden",
    transition: "border-color 0.15s",
  } as CSSProperties,
  recordHeader: {
    padding: "14px 16px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    cursor: "pointer",
    gap: "12px",
  } as CSSProperties,
  recordHeaderLeft: {
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
  } as CSSProperties,
  recordBody: {
    padding: "16px",
    borderTop: "1px solid var(--color-border-subtle, var(--color-border))",
  } as CSSProperties,
  recordQuestion: {
    fontWeight: 500,
    whiteSpace: "nowrap" as const,
    overflow: "hidden",
    textOverflow: "ellipsis",
    fontSize: "14px",
  } as CSSProperties,
  recordContext: {
    fontSize: "13px",
    color: "var(--color-text-secondary)",
    marginBottom: "12px",
    maxHeight: "150px",
    overflow: "auto",
    padding: "10px 12px",
    background: "var(--color-background)",
    borderRadius: "6px",
    border: "1px solid var(--color-border)",
  } as CSSProperties,
  answerBox: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))",
    gap: "12px",
    marginBottom: "12px",
  } as CSSProperties,
  answerSection: {
    padding: "6px 10px",
    borderRadius: "6px",
    background: "var(--color-background)",
    border: "1px solid var(--color-border)",
  } as CSSProperties,
  answerLabel: {
    fontSize: "11px",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    color: "var(--color-text-muted, var(--color-text-secondary))",
    marginBottom: "6px",
    letterSpacing: "0.04em",
  } as CSSProperties,
  answerText: {
    fontSize: "14px",
    wordBreak: "break-word" as const,
    lineHeight: 1.6,
  } as CSSProperties,
  recordMetrics: {
    display: "flex",
    gap: "8px",
    flexWrap: "wrap" as const,
    alignItems: "center",
  } as CSSProperties,
  miniMetric: {
    display: "flex",
    alignItems: "center",
    gap: "4px",
    fontSize: "13px",
    whiteSpace: "nowrap" as const,
  } as CSSProperties,
  score: {
    padding: "2px 8px",
    borderRadius: "4px",
    fontWeight: 600,
    fontFamily: "var(--font-mono)",
    fontSize: "12px",
  } as CSSProperties,
  /** Foundry-style metric badge — outlined, not filled */
  scoreBadge: {
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    padding: "3px 10px",
    borderRadius: "6px",
    fontWeight: 600,
    fontFamily: "var(--font-mono)",
    fontSize: "12px",
    background: "transparent",
    border: "1px solid var(--color-success, #a0d89f)",
    color: "var(--color-success, #a0d89f)",
  } as CSSProperties,
  evaluatorsDetail: {
    marginTop: "12px",
    padding: "14px",
    background: "var(--color-background)",
    borderRadius: "8px",
    border: "1px solid var(--color-border)",
  } as CSSProperties,
  evaluatorsDetailTitle: {
    fontSize: "12px",
    fontWeight: 600,
    marginBottom: "10px",
    color: "var(--color-text-muted, var(--color-text-secondary))",
    textTransform: "uppercase" as const,
    letterSpacing: "0.04em",
  } as CSSProperties,
  evaluatorsDetailGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
    gap: "10px",
  } as CSSProperties,
  expandIcon: {
    fontSize: "12px",
    color: "var(--color-text-muted, var(--color-text-secondary))",
    flexShrink: 0,
    transition: "transform 0.15s",
  } as CSSProperties,
  filterBar: {
    display: "flex",
    gap: "12px",
    marginBottom: "16px",
    flexWrap: "wrap" as const,
    alignItems: "center",
  } as CSSProperties,
  searchInput: {
    flex: "1 1 300px",
    padding: "8px 12px",
    borderRadius: "6px",
    border: "1px solid var(--color-border)",
    background: "#141414",
    color: "var(--color-text-primary)",
    fontSize: "14px",
    minWidth: "200px",
    outline: "none",
  } as CSSProperties,
  pagination: {
    display: "flex",
    justifyContent: "flex-end",
    alignItems: "center",
    gap: "8px",
    marginTop: "16px",
    flexWrap: "wrap" as const,
  } as CSSProperties,
  pageButton: {
    padding: "6px 12px",
    borderRadius: "6px",
    border: "1px solid var(--color-border)",
    background: "transparent",
    color: "var(--color-text-secondary)",
    cursor: "pointer",
    fontSize: "13px",
    transition: "all 0.15s",
  } as CSSProperties,
  pageButtonActive: {
    background: "var(--color-accent)",
    color: "#fff",
    borderColor: "var(--color-accent)",
  } as CSSProperties,
  pageButtonDisabled: {
    opacity: 0.4,
    cursor: "not-allowed",
  } as CSSProperties,
  pageInfo: {
    fontSize: "13px",
    color: "var(--color-text-muted, var(--color-text-secondary))",
    padding: "0 8px",
  } as CSSProperties,
  pageSizeSelect: {
    padding: "6px 10px",
    borderRadius: "6px",
    border: "1px solid var(--color-border)",
    background: "var(--color-background-secondary)",
    color: "var(--color-text-primary)",
    fontSize: "13px",
    cursor: "pointer",
  } as CSSProperties,
};

// =============================================================================
// Utility Functions
// =============================================================================

function getBaselineColor(value: number, baselineValue: number, evaluatorKey: string): string | undefined {
  const delta = value - baselineValue;
  if (Math.abs(delta) < 0.0005) return undefined;
  const better = isHigherBetter(evaluatorKey) ? delta > 0 : delta < 0;
  return better ? "var(--color-success)" : "var(--color-error)";
}

function formatMetricName(key: string): string {
  return key
    .replace(/_mean$/, "")
    .replace(/_sum$/, "")
    .replace(/_median$/, "")
    .replace(/_count$/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (l) => l.toUpperCase());
}

function formatEvaluatorValue(value: number): string {
  if (Math.abs(value) > 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (Math.abs(value) < 0.01 && value !== 0) return value.toExponential(2);
  return value.toFixed(3);
}

/** Extract the primary numeric score from an evaluator result dict.
 *  Mirrors the Python _extract_score / _find_primary_score heuristic and
 *  the Foundry PythonGrader pass-through logic. */
function extractPrimaryScore(evalValue: Record<string, unknown>, evaluatorKey?: string): number | null {
  if (typeof evalValue === "number") return evalValue as number;
  if (typeof evalValue !== "object" || evalValue === null) return null;
  // 1. Try evaluator name as key (e.g. evaluators.coherence.coherence)
  if (evaluatorKey) {
    const v = evalValue[evaluatorKey];
    if (typeof v === "number") return v;
  }
  // 2. Try common keys: score, value
  for (const k of ["score", "value"]) {
    const v = evalValue[k];
    if (typeof v === "number") return v;
  }
  // 3. First numeric value (skip strings, booleans, objects)
  for (const v of Object.values(evalValue)) {
    if (typeof v === "number") return v;
  }
  return null;
}

/** Compute real per-record pass rate using explicit result fields or score thresholds. */
function computePassRate(model: ModelData, evaluatorKey: string): { passed: number; total: number } {
  const records = model.records || [];
  let passed = 0;
  let total = 0;
  for (const record of records) {
    const evalData = (record.evaluators || {})[evaluatorKey];
    if (!evalData) continue;
    total++;
    if (isRecordPass(evalData, evaluatorKey)) passed++;
  }
  // Fall back to record count if no evaluator data found
  if (total === 0) total = model.summary.aggregated_evaluators.number_of_records || records.length || 1;
  return { passed, total };
}

/** Determine if a single evaluator record is a pass.
 *  1. Check for explicit _result field ("pass"/"fail") from the evaluator backend
 *  2. Check well-known typed fields (score, f1_score, match)
 *  3. Fall back to first numeric value with range-based threshold */
function isRecordPass(evalData: EvaluatorValue, evaluatorKey?: string): boolean {
  // 1. Explicit _result field (set by SDK evaluators with threshold logic)
  const resultEntry = Object.entries(evalData).find(([k, v]) => k.endsWith("_result") && typeof v === "string");
  if (resultEntry) return resultEntry[1] === "pass";
  // 2. Well-known typed fields
  if (typeof evalData.score === "number") return evalData.score >= 3;
  if (typeof evalData.f1_score === "number") return evalData.f1_score >= 0.5;
  if (typeof evalData.match === "boolean") return evalData.match;
  // 3. First numeric value — use range-based threshold
  const score = extractPrimaryScore(evalData, evaluatorKey);
  if (score === null) return false;
  return score >= 0 && score <= 1 ? score >= 0.5 : score >= 3;
}

/** Format overview values like counts and response times as clean integers. */
function formatOverviewValue(value: number, evaluatorKey: string): string {
  if (evaluatorKey === "average_response_time_ms") return `${value.toFixed(0)} ms`;
  if (evaluatorKey === "number_of_records") return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return formatEvaluatorValue(value);
}

/** Get a short display name for a model, preferring model_display_name over model_name */
function getDisplayName(model: ModelData): string {
  const name = model.model_display_name || model.model_name;
  if (name.length <= 40) return name;
  return name.slice(0, 37) + "\u2026";
}

/** Get the full (untruncated) display name for tooltips */
function getFullDisplayName(model: ModelData): string {
  return model.model_display_name || model.model_name;
}

/** Group models by tags.model_name */
function groupModels(models: ModelData[]): ModelGroup[] {
  const groups = new Map<string, ModelData[]>();
  for (const model of models) {
    const groupName = String(model.summary.tags.model_name || "ungrouped");
    const existing = groups.get(groupName) || [];
    existing.push(model);
    groups.set(groupName, existing);
  }
  return Array.from(groups.entries()).map(([groupName, models]) => ({ groupName, models }));
}

/** Collect all unique metric keys across all models */
function collectAllMetricKeys(models: ModelData[]): string[] {
  const keys = new Set<string>();
  for (const model of models) {
    for (const key of Object.keys(model.summary.aggregated_evaluators)) {
      keys.add(key);
    }
  }
  return Array.from(keys);
}

/** Collect all unique tag keys across all models (excluding model_name which is used for grouping) */
function collectAllTagKeys(models: ModelData[]): string[] {
  const keys = new Set<string>();
  for (const model of models) {
    for (const key of Object.keys(model.summary.tags)) {
      if (key !== "model_name") keys.add(key);
    }
  }
  return Array.from(keys);
}



/** Check if a metric is "higher is better" (true for most; false for response time, fail counts) */
function isHigherBetter(evaluatorKey: string): boolean {
  const lower = evaluatorKey.toLowerCase();
  if (lower.includes("response_time") || lower.includes("fail count") || lower.includes("tokens")) return false;
  return true;
}

function getRecordSearchableText(record: ExperimentRecord): string {
  const parts = [
    record.record.question,
    record.record.context,
    record.record.ground_truth,
    record.model_name,
    JSON.stringify(record.output),
  ];
  return parts.filter(Boolean).join(" ").toLowerCase();
}

function getEvaluatorSummary(
  evaluators: Record<string, EvaluatorValue>
): Array<{ name: string; value: number | boolean; type: "score" | "boolean" }> {
  const summary: Array<{ name: string; value: number | boolean; type: "score" | "boolean" }> = [];

  for (const [evaluatorName, evaluatorValue] of Object.entries(evaluators)) {
    if (typeof evaluatorValue !== "object" || evaluatorValue === null) continue;

    if (typeof evaluatorValue.score === "number") {
      summary.push({ name: evaluatorName, value: evaluatorValue.score, type: "score" });
    } else if (typeof evaluatorValue.f1_score === "number") {
      summary.push({ name: evaluatorName, value: evaluatorValue.f1_score, type: "score" });
    } else if (typeof evaluatorValue.match === "boolean") {
      summary.push({ name: evaluatorName, value: evaluatorValue.match, type: "boolean" });
    } else {
      // Extract numeric values from nested metric objects (e.g. pass_at_k)
      for (const [subKey, subVal] of Object.entries(evaluatorValue)) {
        if (typeof subVal === "number") {
          summary.push({ name: `${evaluatorName}.${subKey}`, value: subVal, type: "score" });
        } else if (typeof subVal === "object" && subVal !== null && !Array.isArray(subVal)) {
          for (const [innerKey, innerVal] of Object.entries(subVal)) {
            if (typeof innerVal === "number") {
              summary.push({ name: `${evaluatorName}.${subKey}.${innerKey}`, value: innerVal, type: "score" });
            }
          }
        }
      }
    }
  }

  return summary;
}

// =============================================================================
// Components
// =============================================================================

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
const DEFAULT_PAGE_SIZE = 20;

// ---- Record Detail View (for drill-down) ----

interface RecordViewProps {
  record: ExperimentRecord;
  index: number;
}

function RecordView({ record, index }: RecordViewProps) {
  const [expanded, setExpanded] = useState(false);

  const responseTime = record.system_evaluators.response_time?.response_time_ms ?? 0;
  const evaluatorEntries = Object.entries(record.evaluators);
  const evaluatorSummary = getEvaluatorSummary(record.evaluators);

  const displayQuestion =
    record.record.question ||
    (Object.entries(record.record).find(([k, v]) => typeof v === "string" && k !== "context")?.[1] as string) ||
    `Record ${index + 1}`;

  const outputDisplay =
    record.output.response ||
    record.output.answer ||
    (typeof record.output === "string" ? record.output : null);

  const isComplexOutput = outputDisplay === null;
  const formattedOutput = isComplexOutput
    ? JSON.stringify(record.output, null, 2)
    : typeof outputDisplay === "string" ? outputDisplay : JSON.stringify(outputDisplay);

  return (
    <div style={styles.recordCard}>
      <div
        style={styles.recordHeader}
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setExpanded(!expanded)}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`Record: ${displayQuestion}. ${expanded ? "Collapse" : "Expand"} for details.`}
      >
        <div style={styles.recordHeaderLeft}>
          <div style={styles.recordQuestion} title={displayQuestion}>
            {displayQuestion}
          </div>
        </div>
        <div style={styles.recordMetrics}>
          {evaluatorSummary.map((metric) => (
            <span key={metric.name} style={styles.miniMetric}>
              <span style={{ color: "var(--color-text-muted, var(--color-text-secondary))", fontSize: "12px" }}>
                {formatMetricName(metric.name).replace(/ /g, "").slice(0, 12)}
              </span>
              {metric.type === "boolean" ? (
                <span
                  style={{
                    ...styles.scoreBadge,
                    border: metric.value
                      ? "1px solid var(--color-success, #a0d89f)"
                      : "1px solid var(--color-error, #e74856)",
                    color: metric.value ? "var(--color-success, #a0d89f)" : "var(--color-error, #e74856)",
                    background: "transparent",
                  }}
                >
                  {metric.value ? "\u2713 Pass" : "\u2717 Fail"}
                </span>
              ) : (
                <span
                  style={{
                    ...styles.scoreBadge,
                  }}
                >
                  {formatEvaluatorValue(metric.value as number)}
                </span>
              )}
            </span>
          ))}
          <span style={styles.miniMetric}>
            <span style={{
              ...styles.scoreBadge,
              background: "color-mix(in srgb, var(--color-text-secondary) 10%, transparent)",
              color: "var(--color-text-secondary)",
            }}>
              {responseTime < 1 ? `${(responseTime * 1000).toFixed(0)}\u03BCs` : `${responseTime.toFixed(0)}ms`}
            </span>
          </span>
          <span style={styles.expandIcon}>{expanded ? "\u25BC" : "\u25B6"}</span>
        </div>
      </div>

      {expanded && (
        <div style={styles.recordBody}>
          {record.record.context && (
            <div style={styles.recordContext}>
              <strong>Context:</strong> {record.record.context}
            </div>
          )}

          <div style={styles.answerBox}>
            {record.record.ground_truth && (
              <div style={styles.answerSection}>
                <div style={styles.answerLabel}>Ground Truth</div>
                <div style={styles.answerText}>{record.record.ground_truth}</div>
              </div>
            )}
            <div style={styles.answerSection}>
              <div style={styles.answerLabel}>Model Output</div>
              {isComplexOutput ? (
                <pre style={{ ...styles.answerText, whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "12px", maxHeight: "400px", overflow: "auto" }}>
                  {formattedOutput}
                </pre>
              ) : (
                <div style={styles.answerText}>
                  {formattedOutput}
                </div>
              )}
            </div>
          </div>

          {evaluatorEntries.length > 0 && (
            <div style={styles.evaluatorsDetail}>
              <div style={styles.evaluatorsDetailTitle}>Evaluators</div>
              <div style={styles.evaluatorsDetailGrid}>
                {evaluatorEntries.map(([name, value]) => (
                  <div key={name}>
                    <div style={{ fontSize: "11px", color: "var(--color-text-secondary)" }}>
                      {formatMetricName(name)}
                    </div>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "13px" }}>
                      {typeof value === "object" && value !== null
                        ? Object.entries(value).map(([k, v]) => (
                            <div key={k}>
                              {k}: {typeof v === "number" ? formatEvaluatorValue(v) : typeof v === "object" && v !== null ? JSON.stringify(v, null, 2) : String(v)}
                            </div>
                          ))
                        : String(value)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {Object.keys(record.metadata).length > 0 && (
            <div style={{ marginTop: "8px", fontSize: "12px", color: "var(--color-text-secondary)" }}>
              <strong>Metadata:</strong> {JSON.stringify(record.metadata)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Get baseline column border styles based on position in the column */
function getBaselineBorderStyle(isBaseline: boolean, position: "top" | "middle"): CSSProperties {
  if (!isBaseline) return {};
  const style: CSSProperties = {
    background: "rgba(201, 170, 249, 0.06)",
  };
  if (position === "top") {
    return { ...style, boxShadow: "inset 0 3px 0 0 var(--color-accent, #c9aaf9)" };
  }
  return style;
}

// ---- Drill-Down Panel (Foundry-style horizontal table) ----

interface DrillDownPanelProps {
  model: ModelData;
  onClose: () => void;
}

/** Syntax-highlight JSON string with colored spans */
function ColorizedJson({ data }: { data: unknown }) {
  const json = JSON.stringify(data, null, 2);
  const parts: Array<{ text: string; color: string }> = [];
  let i = 0;
  while (i < json.length) {
    const ch = json[i];
    if (ch === '"') {
      // Find closing quote
      let j = i + 1;
      while (j < json.length && json[j] !== '"') { if (json[j] === '\\') j++; j++; }
      const str = json.slice(i, j + 1);
      // Check if it's a key (followed by ':')
      const after = json.slice(j + 1).trimStart();
      if (after.startsWith(':')) {
        parts.push({ text: str, color: "#c9aaf9" }); // purple for keys
      } else {
        parts.push({ text: str, color: "#a0d89f" }); // green for string values
      }
      i = j + 1;
    } else if (/[0-9.\-]/.test(ch) && (i === 0 || /[\s,:\[]/.test(json[i - 1]))) {
      let j = i;
      while (j < json.length && /[0-9.eE\-+]/.test(json[j])) j++;
      parts.push({ text: json.slice(i, j), color: "#f2c661" }); // yellow for numbers
      i = j;
    } else if (json.slice(i, i + 4) === 'true') {
      parts.push({ text: "true", color: "#a0d89f" });
      i += 4;
    } else if (json.slice(i, i + 5) === 'false') {
      parts.push({ text: "false", color: "#e74856" });
      i += 5;
    } else if (json.slice(i, i + 4) === 'null') {
      parts.push({ text: "null", color: "#8a8a8a" });
      i += 4;
    } else {
      // Accumulate plain characters
      if (parts.length > 0 && parts[parts.length - 1].color === "#8a8a8a") {
        parts[parts.length - 1].text += ch;
      } else {
        parts.push({ text: ch, color: "#8a8a8a" });
      }
      i++;
    }
  }
  return (
    <>
      {parts.map((p, idx) => (
        <span key={idx} style={{ color: p.color }}>{p.text}</span>
      ))}
    </>
  );
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "…";
}

/** Get the "Passed" display: e.g. "2/2" or "3/4" based on how many metrics passed threshold */
function getPassedDisplay(record: ExperimentRecord): { text: string; allPassed: boolean } {
  const evaluators = getEvaluatorSummary(record.evaluators);
  if (evaluators.length === 0) return { text: "—", allPassed: true };
  const total = evaluators.length;
  const passed = evaluators.filter((m) => {
    if (m.type === "boolean") return m.value === true;
    if (typeof m.value === "number") {
      // 0-1 scale (f1, precision, recall): pass if >= 0.5
      if (m.value >= 0 && m.value <= 1) return m.value >= 0.5;
      // 1-5 scale: pass if >= 3
      return m.value >= 3;
    }
    return false;
  }).length;
  return { text: `${passed}/${total}`, allPassed: passed === total };
}

function DrillDownPanel({ model, onClose }: DrillDownPanelProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const [showRaw, setShowRaw] = useState(false);

  const toggleRowExpand = (globalIndex: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(globalIndex)) next.delete(globalIndex);
      else next.add(globalIndex);
      return next;
    });
  };

  const totalPages = Math.ceil(model.records.length / pageSize);
  const paginatedRecords = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return model.records.slice(start, start + pageSize);
  }, [model.records, currentPage, pageSize]);

  useEffect(() => {
    setCurrentPage(1);
  }, [pageSize]);

  // Collect all record field keys and metric keys
  const recordFieldKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const r of model.records) {
      for (const k of Object.keys(r.record)) {
        keys.add(k);
      }
    }
    return Array.from(keys);
  }, [model.records]);

  const evaluatorKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const r of model.records) {
      for (const k of Object.keys(r.evaluators)) {
        keys.add(k);
      }
    }
    return Array.from(keys);
  }, [model.records]);

  function renderEvaluatorBadge(evaluatorValue: EvaluatorValue) {
    const passStyle = { ...styles.scoreBadge, border: "1px solid var(--color-success, #a0d89f)", color: "var(--color-success, #a0d89f)", background: "transparent", fontSize: "11px" };
    const failStyle = { ...styles.scoreBadge, border: "1px solid var(--color-error, #e74856)", color: "var(--color-error, #e74856)", background: "transparent", fontSize: "11px" };

    // 1. Check for explicit _result field from evaluator backend (authoritative pass/fail)
    const resultEntry = Object.entries(evaluatorValue).find(([k, v]) => k.endsWith("_result") && typeof v === "string");
    if (resultEntry) {
      const isPassed = resultEntry[1] === "pass";
      const scoreEntry = Object.entries(evaluatorValue).find(([k, v]) => k.endsWith("_score") && typeof v === "number");
      const scoreDisplay = scoreEntry ? `: ${typeof scoreEntry[1] === "number" && scoreEntry[1] <= 1 ? (scoreEntry[1] as number).toFixed(3) : scoreEntry[1]}` : "";
      return <span style={isPassed ? passStyle : failStyle}>{isPassed ? "Pass" : "Fail"}{scoreDisplay}</span>;
    }

    // 2. Well-known typed fields
    if (typeof evaluatorValue.score === "number") {
      const passed = evaluatorValue.score >= 3;
      return <span style={passed ? passStyle : failStyle}>{passed ? "Pass" : "Fail"}: {evaluatorValue.score}</span>;
    }
    if (typeof evaluatorValue.f1_score === "number") {
      const passed = evaluatorValue.f1_score >= 0.5;
      return <span style={passed ? passStyle : failStyle}>{passed ? "Pass" : "Fail"}: {evaluatorValue.f1_score.toFixed(3)}</span>;
    }
    if (typeof evaluatorValue.match === "boolean") {
      return <span style={evaluatorValue.match ? passStyle : failStyle}>{evaluatorValue.match ? "Pass" : "Fail"}</span>;
    }
    // 3. First numeric value — range-based threshold
    const numericVal = Object.values(evaluatorValue).find((v) => typeof v === "number") as number | undefined;
    if (typeof numericVal === "number") {
      const passed = numericVal >= 0 && numericVal <= 1 ? numericVal >= 0.5 : numericVal >= 3;
      return <span style={passed ? passStyle : failStyle}>{passed ? "Pass" : "Fail"}: {numericVal <= 1 ? numericVal.toFixed(3) : numericVal}</span>;
    }
    const keys = Object.keys(evaluatorValue).filter((k) => k !== "explanation");
    const summary = keys.slice(0, 2).map((k) => `${k}: ${String(evaluatorValue[k]).slice(0, 20)}`).join(", ");
    return <span style={{ fontSize: "11px", fontFamily: "var(--font-mono)", color: "var(--color-text-secondary)" }}>{summary || "—"}</span>;
  }

  const cellStyle: CSSProperties = {
    padding: "6px 10px",
    borderBottom: "1px solid var(--color-border-subtle, var(--color-border))",
    fontSize: "13px",
    fontWeight: 500,
    verticalAlign: "top",
    whiteSpace: "nowrap" as const,
    overflow: "hidden",
    textOverflow: "ellipsis",
    maxWidth: "250px",
  };

  const truncatedCellStyle: CSSProperties = {
    padding: "6px 10px",
    borderBottom: "1px solid var(--color-border-subtle, var(--color-border))",
    fontSize: "13px",
    fontWeight: 500,
    verticalAlign: "top",
    maxWidth: "180px",
    minWidth: "120px",
    whiteSpace: "nowrap" as const,
    overflow: "hidden",
    textOverflow: "ellipsis",
  };

  return (
    <div>
      {/* Back button */}
      <div style={{ marginBottom: "16px" }}>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "var(--color-text-secondary)",
            cursor: "pointer",
            fontSize: "13px",
            padding: "4px 0",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontFamily: "var(--font-sans)",
          }}
        >
          <span style={{ fontSize: "16px" }}>←</span> Back to runs
        </button>
      </div>

      {/* Run details header */}
      <div style={{
        display: "flex",
        gap: "40px",
        marginBottom: "24px",
        padding: "16px 0",
        borderBottom: "1px solid var(--color-border)",
        flexWrap: "wrap",
      }}>
        <div>
          <div style={{ fontSize: "12px", color: "var(--color-text-muted, var(--color-text-secondary))", marginBottom: "4px" }}>Status</div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--color-success, #a0d89f)", fontWeight: 600 }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M2 8a6 6 0 1 1 12 0A6 6 0 0 1 2 8Zm6-7a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm2.85 5.85a.5.5 0 0 0-.7-.7l-2.9 2.9-1.4-1.4a.5.5 0 1 0-.7.7L6.9 10.1c.2.2.5.2.7 0l3.25-3.25Z"/></svg>
            <span>Completed</span>
          </div>
        </div>
        <div>
          <div style={{ fontSize: "12px", color: "var(--color-text-muted, var(--color-text-secondary))", marginBottom: "4px" }}>Run</div>
          <div>{getDisplayName(model)}</div>
        </div>
        <div>
          <div style={{ fontSize: "12px", color: "var(--color-text-muted, var(--color-text-secondary))", marginBottom: "4px" }}>Records</div>
          <div>{model.records.length}</div>
        </div>
      </div>

      {/* Heading */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", margin: "0 0 16px" }}>
        <h2 style={{ fontSize: "16px", fontWeight: 600, margin: 0 }}>Detailed evaluator results</h2>
        <button
          onClick={() => setShowRaw(!showRaw)}
          style={{
            ...styles.buttonSmall,
            ...(showRaw ? styles.buttonSmallActive : {}),
          }}
        >
          {showRaw ? "Formatted" : "Raw JSON"}
        </button>
      </div>

      {showRaw ? (
        <div style={{
          background: "var(--color-background-secondary)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--border-radius)",
          padding: "16px",
          maxHeight: "600px",
          overflow: "auto",
        }}>
          <pre style={{
            fontSize: "12px",
            fontFamily: "var(--font-mono)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
          }}>
            <ColorizedJson data={paginatedRecords.map((r) => ({
              record: r.record,
              output: r.output,
              evaluators: r.evaluators,
              model: r.model_name,
            }))} />
          </pre>
        </div>
      ) : (
        <>
      {/* Horizontal results table */}
      <div style={{ ...styles.tableWrapper, overflowX: "auto" }}>
        <table style={{ ...styles.table, minWidth: "100%" }}>
          <thead>
            <tr>
              {recordFieldKeys.map((k) => (
                <th key={k} style={{ ...styles.th, textTransform: "none" as const, minWidth: "120px" }}>{k}</th>
              ))}
              <th style={{ ...styles.th, textTransform: "none" as const, minWidth: "150px" }}>Output</th>
              {evaluatorKeys.map((k) => (
                <th key={k} style={{ ...styles.th, textTransform: "none" as const, minWidth: "90px" }}>
                  {formatMetricName(k)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedRecords.map((record, idx) => {
              const globalIdx = (currentPage - 1) * pageSize + idx;
              const isExpanded = expandedRows.has(globalIdx);
              const outputText =
                typeof record.output === "string"
                  ? record.output
                  : record.output.response || record.output.answer || JSON.stringify(record.output);

              const expandedCellStyle: CSSProperties = {
                ...truncatedCellStyle,
                whiteSpace: "pre-wrap",
                overflow: "hidden",
                textOverflow: "clip",
                maxWidth: "300px",
                maxHeight: "150px",
                wordBreak: "break-word",
              };

              const rowCellStyle = isExpanded ? expandedCellStyle : truncatedCellStyle;
              const rowDataCellStyle = isExpanded
                ? { ...cellStyle, whiteSpace: "pre-wrap" as const, overflow: "hidden" as const, textOverflow: "clip" as const, maxHeight: "150px" }
                : cellStyle;

              return (
                <tr
                  key={`${record.run_id}-${globalIdx}`}
                  onClick={() => toggleRowExpand(globalIdx)}
                  style={{
                    cursor: "pointer",
                    transition: "background 0.1s",
                    background: isExpanded ? "var(--color-background-secondary)" : "transparent",
                  }}
                  onMouseEnter={(e) => { if (!isExpanded) e.currentTarget.style.background = "var(--color-background-tertiary)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = isExpanded ? "var(--color-background-secondary)" : "transparent"; }}
                  title={isExpanded ? "Click to collapse" : "Click to expand full content"}
                >
                  {recordFieldKeys.map((k) => {
                    const cellVal = record.record[k];
                    const cellStr = cellVal == null ? "" : typeof cellVal === "object" ? JSON.stringify(cellVal) : String(cellVal);
                    return (
                      <td key={k} style={rowCellStyle} title={isExpanded ? undefined : cellStr}>
                        {isExpanded ? cellStr : truncate(cellStr, 60)}
                      </td>
                    );
                  })}
                  <td style={rowCellStyle} title={isExpanded ? undefined : String(outputText)}>
                    {isExpanded ? String(outputText) : truncate(String(outputText), 60)}
                  </td>
                  {evaluatorKeys.map((k) => (
                    <td key={k} style={{ ...rowDataCellStyle, textAlign: "center" }}>
                      {record.evaluators[k] ? renderEvaluatorBadge(record.evaluators[k]) : "—"}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
        </>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ ...styles.pagination, padding: "12px 0" }}>
          <button
            style={{ ...styles.pageButton, ...(currentPage === 1 ? styles.pageButtonDisabled : {}) }}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
          >
            ‹ Prev
          </button>
          <span style={styles.pageInfo}>Page {currentPage} of {totalPages}</span>
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            style={styles.pageSizeSelect}
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>{size} / page</option>
            ))}
          </select>
          <button
            style={{ ...styles.pageButton, ...(currentPage === totalPages ? styles.pageButtonDisabled : {}) }}
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
          >
            Next ›
          </button>
        </div>
      )}
    </div>
  );
}

// ---- Delta Display Component ----

interface DeltaValueProps {
  value: number;
  baselineValue: number;
  evaluatorKey: string;
}

function DeltaValue({ value, baselineValue, evaluatorKey }: DeltaValueProps) {
  const delta = value - baselineValue;

  if (Math.abs(delta) < 0.0005) {
    return (
      <span style={styles.deltaNeutral}>
        {"0.000 -"}
      </span>
    );
  }

  const isUp = delta > 0;
  const isBetter = isHigherBetter(evaluatorKey) ? isUp : !isUp;
  const arrow = isUp ? "▲" : "▼";
  const formatted = (isUp ? "+" : "") + formatEvaluatorValue(delta);

  return (
    <span style={isBetter ? styles.deltaPositive : styles.deltaNegative}>
      {formatted} {arrow}
    </span>
  );
}

// ---- Best-in-row highlighting ----

/** Find the index of the best value for a metric across all models */
function findBestModelIndex(models: ModelData[], evaluatorKey: string): number | null {
  const higherBetter = isHigherBetter(evaluatorKey);
  let bestIdx: number | null = null;
  let bestVal: number | null = null;

  for (let i = 0; i < models.length; i++) {
    const val = models[i].summary.aggregated_evaluators[evaluatorKey];
    if (val === undefined) continue;
    if (bestVal === null || (higherBetter ? val > bestVal : val < bestVal)) {
      bestVal = val;
      bestIdx = i;
    }
  }
  return bestIdx;
}

// ---- Main Comparison Table ----

interface ComparisonTableProps {
  data: ViewResultsData;
  onRefresh?: () => void;
}

function ComparisonTable({ data, onRefresh }: ComparisonTableProps) {
  const models = Array.isArray(data.models) && data.models.length > 0
    ? data.models
    : data.summary && data.records
      ? [{
          model_name: data.summary.run_id,
          summary: data.summary,
          records: data.records,
          files: { summary: "", records: null },
        }]
      : [];

  // Empty state: no models at all
  if (models.length === 0) {
    return (
      <div>
        <div style={styles.header}>
          <div style={styles.headerTop}>
            <div>
              <h1 style={styles.title}>Evaluation runs</h1>
              <p style={styles.subtitle}>No evaluation results yet. Run an evaluation to see results here.</p>
            </div>
            {onRefresh && (
              <button style={styles.button} onClick={onRefresh}>{"↻ Refresh"}</button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const [baselineIndex, setBaselineIndex] = useState<number | null>(null);
  const [drillDownModel, setDrillDownModel] = useState<ModelData | null>(null);
  const [hiddenEvaluators, setHiddenEvaluators] = useState<Set<string>>(new Set());
  const [expandedTags, setExpandedTags] = useState<Set<string>>(new Set());

  // Group models by model_name tag
  const groups = useMemo(() => groupModels(models), [models]);

  // Collect all metric keys and tag keys
  const allMetricKeys = useMemo(() => collectAllMetricKeys(models), [models]);
  const allTagKeys = useMemo(() => collectAllTagKeys(models), [models]);

  // Separate metrics into categories
  const overviewKeys = ["number_of_records", "average_response_time_ms"];
  const failKeys = allMetricKeys.filter((k) => k.toLowerCase().includes("fail count"));
  const scoreKeys = allMetricKeys.filter((k) => !overviewKeys.includes(k) && !failKeys.includes(k));

  // Visible metric keys
  const visibleScoreKeys = scoreKeys.filter((k) => !hiddenEvaluators.has(k));
  const visibleFailKeys = failKeys.filter((k) => !hiddenEvaluators.has(k));

  const toggleMetricVisibility = (key: string) => {
    setHiddenEvaluators((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // Flat ordered list of models for column indexing
  const flatModels = useMemo(() => groups.flatMap((g) => g.models), [groups]);

  // Auto-detect baseline: prefer "baseline_model", fall back to first model
  useEffect(() => {
    if (baselineIndex !== null) return;
    if (flatModels.length === 0) return;
    const idx = flatModels.findIndex(
      (m) =>
        m.model_name.toLowerCase() === "baseline_model" ||
        String(m.summary.tags.model_name || "").toLowerCase() === "baseline_model"
    );
    setBaselineIndex(idx >= 0 ? idx : 0);
  }, [flatModels, baselineIndex]);

  const baselineEvaluators = baselineIndex !== null ? flatModels[baselineIndex]?.summary.aggregated_evaluators : null;

  // Build column headers with group spans
  const totalCols = flatModels.length + 1; // +1 for metric label column

  return (
    <div>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerTop}>
          <div>
            <h1 style={styles.title}>Evaluation runs</h1>
            <p style={styles.subtitle}>
              {flatModels.length > 1
                ? `Compare ${flatModels.length} runs across ${groups.length} model${groups.length > 1 ? "s" : ""}`
                : "Select multiple runs to compare results statistically"}
            </p>
            <p style={{
              fontSize: "12px",
              color: "var(--color-text-muted, var(--color-text-secondary))",
              margin: "4px 0 0",
              fontFamily: "var(--font-mono)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              maxWidth: "100%",
            }}>
              {(data.output_path || "").split("/").pop()}
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center", flexShrink: 0 }}>
            {onRefresh && (
              <button style={styles.button} onClick={onRefresh}>
                {"↻ Refresh"}
              </button>
            )}
          </div>
        </div>

        {/* Show "Open in Browser" hint only when running in MCP (not standalone CLI) */}
        {onRefresh && !window.__EVEE_RESULTS_DATA__ && (() => {
          const relativePath = (() => {
            const p = data.output_path || "";
            const expIdx = p.indexOf("experiment/");
            return expIdx !== -1 ? p.substring(expIdx) : p.split("/").slice(-3).join("/");
          })();
          const cmd = `evee view ${relativePath}`;
          return (
            <div style={{
              fontSize: "12px",
              color: "var(--color-text-muted, var(--color-text-secondary))",
              marginTop: "8px",
              padding: "8px 12px",
              borderLeft: "3px solid var(--color-accent)",
              borderLeft: "3px solid var(--color-accent, #c9aaf9)",
              borderRadius: "0 6px 6px 0",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}>
              <span>
                <strong>Tip:</strong>{" "}
                Run <code style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text-primary)" }}>
                  {cmd}
                </code> to open this view in your browser
              </span>
              <button
                style={{
                  background: "none",
                  border: "1px solid var(--color-border)",
                  borderRadius: "3px",
                  cursor: "pointer",
                  padding: "1px 5px",
                  fontSize: "11px",
                  color: "var(--color-text-secondary)",
                  flexShrink: 0,
                }}
                title="Copy command"
                onClick={() => {
                  navigator.clipboard.writeText(cmd);
                }}
              >
                {"📋"}
              </button>
            </div>
          );
        })()}

        {/* Metric visibility toggles */}
        {allMetricKeys.length > 8 && (
          <div style={{ marginTop: "12px" }}>
            <span style={{ fontSize: "12px", color: "var(--color-text-secondary)", marginRight: "8px" }}>
              Toggle evaluators:
            </span>
            {[...scoreKeys, ...failKeys].map((key) => (
              <button
                key={key}
                style={{
                  ...styles.buttonSmall,
                  marginRight: "4px",
                  marginBottom: "4px",
                  opacity: hiddenEvaluators.has(key) ? 0.4 : 1,
                  textDecoration: hiddenEvaluators.has(key) ? "line-through" : "none",
                }}
                onClick={() => toggleMetricVisibility(key)}
              >
                {formatMetricName(key)}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Comparison Table */}
      <div style={styles.tableWrapper}>
        <table style={styles.table}>
          <thead>
            {/* Group header row */}
            {groups.length > 1 && (
              <tr>
                <th style={{ ...styles.th, ...styles.thMetricLabel, borderRight: "2px solid var(--color-border)" }} />
                {groups.map((group) => (
                  <th
                    key={group.groupName}
                    colSpan={group.models.length}
                    style={{
                      ...styles.groupHeader,
                      textAlign: "center",
                      borderLeft: "2px solid var(--color-border)",
                    }}
                  >
                    {group.groupName}
                  </th>
                ))}
              </tr>
            )}

            {/* Column headers (one per model variant) */}
            <tr>
              <th style={{ ...styles.th, ...styles.thMetricLabel, borderRight: "2px solid var(--color-border)" }}>
                Metric
              </th>
              {flatModels.map((model, idx) => {
                const isBaseline = baselineIndex === idx;
                const isFirstInGroup =
                  groups.length > 1 && groups.some((g) => g.models[0] === model);

                return (
                  <th
                    key={idx}
                    style={{
                      ...styles.columnHeader,
                      ...(isFirstInGroup ? { borderLeft: "2px solid var(--color-border)" } : {}),
                      ...getBaselineBorderStyle(isBaseline, "top"),
                    }}
                    title={getFullDisplayName(model)}
                  >
                    <div>{getDisplayName(model)}</div>
                    <div style={{ marginTop: "4px", display: "flex", gap: "4px", justifyContent: "center" }}>
                      {isBaseline && <span style={styles.baselineTag}>baseline</span>}
                      <button
                        style={{
                          ...styles.buttonSmall,
                          fontSize: "10px",
                          padding: "1px 6px",
                          ...(isBaseline ? styles.buttonSmallActive : {}),
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setBaselineIndex(isBaseline ? null : idx);
                        }}
                        title={isBaseline ? "Remove baseline" : "Set as baseline"}
                        aria-label={isBaseline ? "Remove baseline" : "Set as baseline"}
                      >
                        {isBaseline ? "\u2605" : "\u2606"}
                      </button>
                      <button
                        style={{
                          ...styles.buttonSmall,
                          fontSize: "10px",
                          padding: "1px 6px",
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setDrillDownModel(model);
                        }}
                        title="View individual records"
                        aria-label="View individual records"
                      >
                        {"\u25B6"}
                      </button>
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>

          <tbody>
            {/* Parameters section */}
            {allTagKeys.length > 0 && (
              <>
                <tr>
                  <td
                    colSpan={totalCols}
                    style={{ ...styles.sectionRow, padding: "8px 16px" }}
                  >
                    Parameters
                  </td>
                </tr>
                {allTagKeys.map((tagKey) => {
                  const isExpanded = expandedTags.has(tagKey);
                  const hasLongValues = flatModels.some(
                    (m) => String(m.summary.tags[tagKey] ?? "").length > 30
                  );
                  const toggleExpand = () => {
                    setExpandedTags((prev) => {
                      const next = new Set(prev);
                      if (next.has(tagKey)) next.delete(tagKey);
                      else next.add(tagKey);
                      return next;
                    });
                  };
                  return (
                  <tr
                    key={`tag-${tagKey}`}
                    onClick={hasLongValues ? toggleExpand : undefined}
                    style={hasLongValues ? { cursor: "pointer" } : undefined}
                  >
                    <td style={styles.thMetricLabel}>
                      <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        {hasLongValues && (
                          <span style={{ fontSize: "11px", flexShrink: 0, opacity: 0.7 }}>
                            {isExpanded ? "▼" : "▶"}
                          </span>
                        )}
                        {tagKey}
                      </span>
                    </td>
                    {flatModels.map((model, idx) => {
                      const isFirstInGroup =
                        groups.length > 1 && groups.some((g) => g.models[0] === model);
                      const isBaseline = baselineIndex === idx;
                      const cellValue = String(model.summary.tags[tagKey] ?? "\u2014");
                      return (
                        <td
                          key={idx}
                          style={{
                            ...styles.td,
                            textAlign: "center",
                            fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
                            fontWeight: 500,
                            ...(isFirstInGroup ? { borderLeft: "2px solid var(--color-border)" } : {}),
                            ...getBaselineBorderStyle(isBaseline, "middle"),
                            ...(isExpanded
                              ? { whiteSpace: "pre-wrap", wordBreak: "break-word" as const, overflow: "visible", maxWidth: "none", textOverflow: "clip" }
                              : {}),
                          }}
                          title={isExpanded ? undefined : cellValue}
                        >
                          {cellValue}
                        </td>
                      );
                    })}
                  </tr>
                  );
                })}
              </>
            )}

            {/* Overview metrics */}
            <tr>
              <td colSpan={totalCols} style={{ ...styles.sectionRow, padding: "8px 16px" }}>
                Overview
              </td>
            </tr>
            {overviewKeys.map((evaluatorKey) => {
              const bestIdx = findBestModelIndex(flatModels, evaluatorKey);
              return (
                <tr key={evaluatorKey}>
                  <td style={styles.thMetricLabel} title={formatMetricName(evaluatorKey)}>{formatMetricName(evaluatorKey)}</td>
                  {flatModels.map((model, idx) => {
                    const val = model.summary.aggregated_evaluators[evaluatorKey];
                    const isFirstInGroup =
                      groups.length > 1 && groups.some((g) => g.models[0] === model);
                    const isBest = bestIdx === idx && flatModels.length > 1;
                    const isBaseline = baselineIndex === idx;
                    return (
                      <td
                        key={idx}
                        style={{
                          ...styles.td,
                          ...(isFirstInGroup ? { borderLeft: "2px solid var(--color-border)" } : {}),
                          ...(isBest ? { fontWeight: 700 } : {}),
                          ...getBaselineBorderStyle(isBaseline, "middle"),
                        }}
                      >
                        {val !== undefined ? (
                          <>
                            {formatOverviewValue(val, evaluatorKey)}
                            {baselineEvaluators && !isBaseline && baselineEvaluators[evaluatorKey] !== undefined && (
                              <DeltaValue
                                value={val}
                                baselineValue={baselineEvaluators[evaluatorKey]}
                                evaluatorKey={evaluatorKey}
                              />
                            )}
                          </>
                        ) : (
                          "\u2014"
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}

            {/* Score metrics */}
            {visibleScoreKeys.length > 0 && (
              <>
                <tr>
                  <td colSpan={totalCols} style={{ ...styles.sectionRow, padding: "8px 16px" }}>
                    Evaluators
                  </td>
                </tr>
                {visibleScoreKeys.map((evaluatorKey) => {
                  const bestIdx = findBestModelIndex(flatModels, evaluatorKey);
                  return (
                    <tr key={evaluatorKey}>
                      <td style={styles.thMetricLabel} title={formatMetricName(evaluatorKey)}>{formatMetricName(evaluatorKey)}</td>
                      {flatModels.map((model, idx) => {
                        const val = model.summary.aggregated_evaluators[evaluatorKey];
                        const isFirstInGroup =
                          groups.length > 1 && groups.some((g) => g.models[0] === model);
                        const isBest = bestIdx === idx && flatModels.length > 1;
                        const isBaseline = baselineIndex === idx;
                        const baselineVal = baselineEvaluators?.[evaluatorKey];
                        const hasComparison = !isBaseline && val !== undefined && baselineVal !== undefined;
                        return (
                          <td
                            key={idx}
                            style={{
                              ...styles.td,
                              ...(isFirstInGroup ? { borderLeft: "2px solid var(--color-border)" } : {}),
                              ...(isBest ? { fontWeight: 700 } : {}),
                              ...getBaselineBorderStyle(isBaseline, "middle"),
                              color: hasComparison
                                ? getBaselineColor(val, baselineVal, evaluatorKey)
                                : val !== undefined ? "var(--color-success)" : undefined,
                            }}
                          >
                            {val !== undefined ? (
                              <>
                                {formatEvaluatorValue(val)}
                                {baselineEvaluators && !isBaseline && baselineEvaluators[evaluatorKey] !== undefined && (
                                  <DeltaValue
                                    value={val}
                                    baselineValue={baselineEvaluators[evaluatorKey]}
                                    evaluatorKey={evaluatorKey}
                                  />
                                )}
                              </>
                            ) : (
                              "\u2014"
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </>
            )}

            {/* Fail count metrics */}
            {visibleFailKeys.length > 0 && (
              <>
                <tr>
                  <td colSpan={totalCols} style={{ ...styles.sectionRow, padding: "8px 16px" }}>
                    Failures
                  </td>
                </tr>
                {visibleFailKeys.map((evaluatorKey) => (
                  <tr key={evaluatorKey}>
                    <td style={styles.thMetricLabel} title={formatMetricName(evaluatorKey)}>{formatMetricName(evaluatorKey)}</td>
                    {flatModels.map((model, idx) => {
                      const val = model.summary.aggregated_evaluators[evaluatorKey];
                      const isFirstInGroup =
                        groups.length > 1 && groups.some((g) => g.models[0] === model);
                      const isBaseline = baselineIndex === idx;
                      return (
                        <td
                          key={idx}
                          style={{
                            ...styles.td,
                            ...(isFirstInGroup ? { borderLeft: "2px solid var(--color-border)" } : {}),
                            ...getBaselineBorderStyle(isBaseline, "middle"),
                            color: val && val > 0 ? "var(--color-error)" : undefined,
                          }}
                        >
                          {val !== undefined ? formatEvaluatorValue(val) : "\u2014"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </>
            )}
          </tbody>
        </table>
      </div>

      {/* Tip */}
      <div
        style={{
          textAlign: "center",
          fontSize: "12px",
          color: "var(--color-text-muted, var(--color-text-secondary))",
          marginTop: "12px",
          padding: "12px",
        }}
      >
        {"Click \u25B6 to view detailed evaluator results for each record"}
        {baselineIndex === null && " \u2022 Click \u2606 to set a baseline for comparison"}
      </div>

      {/* Drill-down overlay */}
      {drillDownModel && (
        <div ref={(el) => { if (el) el.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
          <DrillDownPanel model={drillDownModel} onClose={() => setDrillDownModel(null)} />
        </div>
      )}
    </div>
  );
}

// ---- App Root ----

// Type for injected data from CLI
declare global {
  interface Window {
    __EVEE_RESULTS_DATA__?: ViewResultsData;
    __EVEE_OUTPUT_DIR__?: string;
  }
}

interface ExperimentListItem {
  name: string;
  path: string;
  num_runs?: number;
  created?: number;
  evaluators?: string[];
  dataset?: string;
  status?: string;
}

// ---- Experiments Overview Page (Foundry-style landing) ----

function ExperimentsOverview({
  experiments,
  onSelect,
  onViewDataset,
}: {
  experiments: ExperimentListItem[];
  onSelect: (name: string) => void;
  onViewDataset: (experimentName: string) => void;
}) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const list = search.trim()
      ? experiments.filter((e) => e.name.toLowerCase().includes(search.toLowerCase()))
      : [...experiments];
    // Sort by creation date descending (newest first)
    list.sort((a, b) => (b.created ?? 0) - (a.created ?? 0));
    return list;
  }, [experiments, search]);

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <h1 style={{ fontSize: "20px", fontWeight: 600, margin: "0 0 4px" }}>Evaluations</h1>
        <p style={{ fontSize: "14px", color: "var(--color-text-muted, var(--color-text-secondary))", margin: 0 }}>
          Evaluate the quality of your generative AI applications with industry standard evaluators to compare and choose the best version based on your need.
        </p>
      </div>

      {/* Search bar */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "20px", alignItems: "center" }}>
        <div style={{ position: "relative", flex: 1 }}>
          <span style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--color-text-muted, var(--color-text-secondary))", pointerEvents: "none" }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M11.5 11.5L14 14" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/><circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.2"/></svg>
          </span>
          <input
            type="text"
            placeholder="Search evaluations by name"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              ...styles.searchInput,
              flex: "unset",
              width: "100%",
              paddingLeft: "36px",
              background: "#141414",
            }}
          />
        </div>
      </div>

      {/* Experiments table */}
      <div style={styles.tableWrapper}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={{ ...styles.th, textTransform: "none" as const, fontWeight: 600, color: "#FFFFFF" }}>Name</th>
              <th style={{ ...styles.th, textTransform: "none" as const, fontWeight: 600, color: "#FFFFFF" }}>Dataset</th>
              <th style={{ ...styles.th, textTransform: "none" as const, fontWeight: 600, color: "#FFFFFF" }}>Runs</th>
              <th style={{ ...styles.th, textTransform: "none" as const, fontWeight: 600, color: "#FFFFFF" }}>Status</th>
              <th style={{ ...styles.th, textTransform: "none" as const, fontWeight: 600, color: "#FFFFFF" }}>Created</th>
              <th style={{ ...styles.th, textTransform: "none" as const, fontWeight: 600, color: "#FFFFFF" }}>Evaluators</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((exp) => (
              <tr
                key={exp.name}
                onClick={() => onSelect(exp.name)}
                style={{ cursor: "pointer" }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLTableRowElement).style.background = "var(--color-background-secondary)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLTableRowElement).style.background = "";
                }}
              >
                <td style={{ ...styles.td, textAlign: "left", color: "var(--color-accent)", fontWeight: 500, fontFamily: "var(--font-sans)", padding: "8px 12px" }}>
                  {exp.name}
                </td>
                <td
                  style={{ ...styles.td, textAlign: "left", fontFamily: "var(--font-sans)", padding: "8px 12px" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onViewDataset(exp.name);
                  }}
                >
                  <span
                    style={{
                      color: "var(--color-accent)",
                      cursor: "pointer",
                      fontWeight: 500,
                      textDecoration: "underline",
                      textDecorationColor: "transparent",
                      transition: "text-decoration-color 0.15s",
                    }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLSpanElement).style.textDecorationColor = "var(--color-accent)"; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLSpanElement).style.textDecorationColor = "transparent"; }}
                    title={exp.dataset || exp.name}
                  >
                    {exp.dataset || exp.name}
                  </span>
                </td>
                <td style={{ ...styles.td, textAlign: "center", color: "#FFFFFF", fontFamily: "var(--font-sans)", padding: "8px 12px" }}>
                  {exp.num_runs ?? "—"}
                </td>
                <td style={{ ...styles.td, textAlign: "left", fontFamily: "var(--font-sans)", padding: "8px 12px" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", color: "var(--color-success, #a0d89f)", fontWeight: 600 }}>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M2 8a6 6 0 1 1 12 0A6 6 0 0 1 2 8Zm6-7a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm2.85 5.85a.5.5 0 0 0-.7-.7l-2.9 2.9-1.4-1.4a.5.5 0 1 0-.7.7L6.9 10.1c.2.2.5.2.7 0l3.25-3.25Z"/></svg>
                    <span>{exp.status ?? "Completed"}</span>
                  </span>
                </td>
                <td style={{ ...styles.td, textAlign: "left", color: "#FFFFFF", fontFamily: "var(--font-sans)", padding: "8px 12px" }}>
                  {exp.created ? new Date(exp.created * 1000).toLocaleString() : "—"}
                </td>
                <td style={{ ...styles.td, textAlign: "left", fontFamily: "var(--font-sans)", padding: "8px 12px" }}>
                  <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
                    {(exp.evaluators ?? []).slice(0, 4).map((m) => (
                      <span
                        key={m}
                        style={{
                          ...styles.scoreBadge,
                          fontSize: "11px",
                          padding: "2px 8px",
                        }}
                      >
                        {formatMetricName(m)}
                      </span>
                    ))}
                    {(exp.evaluators ?? []).length > 4 && (
                      <span style={{ fontSize: "11px", color: "var(--color-text-muted, var(--color-text-secondary))" }}>
                        +{(exp.evaluators ?? []).length - 4}
                      </span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filtered.length === 0 && (
        <div style={{ textAlign: "center", padding: "40px", color: "var(--color-text-muted, var(--color-text-secondary))" }}>
          {search ? "No evaluations match your search." : "No evaluations found."}
        </div>
      )}
    </div>
  );
}

// ---- Experiment Detail Page (Foundry-style runs table + evaluators) ----

function ExperimentDetail({
  data,
  onBack,
  onCompare,
}: {
  data: ViewResultsData;
  onBack?: () => void;
  onCompare: () => void;
}) {
  const models = Array.isArray(data.models) ? data.models : [];
  const experimentName = (data.output_path || "").split("/").pop() || "Experiment";
  const [drillDownModel, setDrillDownModel] = useState<ModelData | null>(null);
  const [showRunsRaw, setShowRunsRaw] = useState(false);
  const [datasetExpanded, setDatasetExpanded] = useState(false);
  const [datasetPage, setDatasetPage] = useState(1);
  const [datasetPageSize, setDatasetPageSize] = useState(DEFAULT_PAGE_SIZE);

  // Collect unique dataset records (deduplicate across models using first model's records)
  const datasetRecords = useMemo(() => {
    if (models.length === 0) return [];
    return models[0].records.map((r) => r.record);
  }, [models]);

  const datasetColumns = useMemo(() => {
    const keys = new Set<string>();
    for (const rec of datasetRecords) {
      for (const k of Object.keys(rec)) keys.add(k);
    }
    return Array.from(keys);
  }, [datasetRecords]);

  const datasetTotalPages = Math.ceil(datasetRecords.length / datasetPageSize);
  const paginatedDatasetRecords = useMemo(() => {
    const start = (datasetPage - 1) * datasetPageSize;
    return datasetRecords.slice(start, start + datasetPageSize);
  }, [datasetRecords, datasetPage, datasetPageSize]);

  useEffect(() => {
    setDatasetPage(1);
  }, [datasetPageSize]);

  // Dataset name from the output path
  const datasetName = useMemo(() => {
    const path = data.output_path || "";
    const parts = path.split("/");
    return parts.length > 1 ? parts[parts.length - 2] : parts[0] || "Dataset";
  }, [data.output_path]);

  // Empty state: no models/runs
  if (models.length === 0) {
    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "20px" }}>
          {onBack && (
            <button
              onClick={onBack}
              style={{
                background: "none",
                border: "none",
                color: "var(--color-text-primary)",
                cursor: "pointer",
                fontSize: "20px",
                padding: "12px",
                lineHeight: 1,
                minWidth: "44px",
                minHeight: "44px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              ←
            </button>
          )}
          <h1 style={{ fontSize: "18px", fontWeight: 600, margin: 0 }}>{experimentName}</h1>
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "60px 20px",
            gap: "16px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "14px", color: "var(--color-text-muted, var(--color-text-secondary))" }}>
            No evaluation results yet. Run an evaluation to see results here.
          </div>
        </div>
      </div>
    );
  }
  const allMetricKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const model of models) {
      for (const key of Object.keys(model.summary.aggregated_evaluators)) {
        if (key !== "number_of_records" && key !== "average_response_time_ms" && !key.toLowerCase().includes("fail"))
          keys.add(key);
      }
    }
    return Array.from(keys);
  }, [models]);

  // Collect evaluator info from metric names
  const evaluators = useMemo(() => {
    return allMetricKeys.map((k) => ({
      name: formatMetricName(k).replace(/ \(avg\)$/, "").replace(/ Mean$/, ""),
      rawName: k.replace(/_mean$/, "").replace(/_avg$/, ""),
      type: "python",
    }));
  }, [allMetricKeys]);

  /** Format a metric as "percentage\n pass/total" like Foundry's "100% 10/10".
   *  Computes real per-record pass rates (positive score = pass) instead of
   *  deriving from the mean — matching Foundry portal behavior exactly. */
  function formatEvaluatorAsPassRate(model: ModelData, evaluatorKey: string): { pct: string; detail: string; allPassed: boolean } | null {
    const val = model.summary.aggregated_evaluators[evaluatorKey];
    if (val === undefined) return null;

    const { passed, total } = computePassRate(model, evaluatorKey);
    const pct = total > 0 ? Math.round((passed / total) * 100) : 0;
    return { pct: `${pct}%`, detail: `${passed} / ${total}`, allPassed: pct === 100 };
  }

  // If a run is selected, show its detailed metrics as full page
  if (drillDownModel) {
    return <DrillDownPanel model={drillDownModel} onClose={() => setDrillDownModel(null)} />;
  }

  return (
    <div>
      {/* Back arrow + experiment name */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "20px" }}>
        {onBack && (
          <button
            onClick={onBack}
            style={{
              background: "none",
              border: "none",
              color: "var(--color-text-primary)",
              cursor: "pointer",
              fontSize: "20px",
              padding: "12px",
              lineHeight: 1,
              minWidth: "44px",
              minHeight: "44px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            ←
          </button>
        )}
        <h1 style={{ fontSize: "18px", fontWeight: 600, margin: 0 }}>{experimentName}</h1>
      </div>

      {/* Evaluation details */}
      <div style={{
        display: "flex",
        gap: "40px",
        marginBottom: "24px",
        padding: "16px 0",
        borderBottom: "1px solid var(--color-border)",
        flexWrap: "wrap",
      }}>
        <div>
          <div style={{ fontSize: "12px", color: "var(--color-text-muted, var(--color-text-secondary))", marginBottom: "4px" }}>Status</div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--color-success, #a0d89f)", fontWeight: 600 }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M2 8a6 6 0 1 1 12 0A6 6 0 0 1 2 8Zm6-7a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm2.85 5.85a.5.5 0 0 0-.7-.7l-2.9 2.9-1.4-1.4a.5.5 0 1 0-.7.7L6.9 10.1c.2.2.5.2.7 0l3.25-3.25Z"/></svg>
              <span>Completed</span>
            </div>
          </div>
        </div>
        <div>
          <div style={{ fontSize: "12px", color: "var(--color-text-muted, var(--color-text-secondary))", marginBottom: "4px" }}>Runs</div>
          <div>{models.length}</div>
        </div>
      </div>

      {/* Runs tab header */}
      <div style={{ borderBottom: "2px solid var(--color-accent)", display: "inline-block", padding: "8px 16px", marginBottom: "20px" }}>
        <span style={{ fontWeight: 600, fontSize: "14px" }}>Runs</span>
      </div>

      {/* Evaluation runs heading */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <div>
          <h2 style={{ fontSize: "16px", fontWeight: 600, margin: "0 0 4px" }}>Evaluation runs</h2>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted, var(--color-text-secondary))", margin: 0 }}>
            Select multiple runs to compare results statistically or use AI to analyze failed tests.
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={() => setShowRunsRaw(!showRunsRaw)}
            style={{
              ...styles.buttonSmall,
              ...(showRunsRaw ? styles.buttonSmallActive : {}),
            }}
          >
            {showRunsRaw ? "Formatted" : "Raw JSON"}
          </button>
          <button style={styles.button} onClick={onCompare}>
            Compare runs
          </button>
        </div>
      </div>

      {showRunsRaw ? (
        <div style={{
          background: "var(--color-background-secondary)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--border-radius)",
          padding: "16px",
          maxHeight: "600px",
          overflow: "auto",
          marginBottom: "24px",
        }}>
          <pre style={{
            fontSize: "12px",
            fontFamily: "var(--font-mono)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
          }}>
            <ColorizedJson data={models.map((m) => ({
              name: m.model_display_name || m.model_name,
              aggregated_evaluators: m.summary.aggregated_evaluators,
              tags: m.summary.tags,
              records_count: m.records.length,
            }))} />
          </pre>
        </div>
      ) : (
        <>
      {/* Runs table */}
      <div style={styles.tableWrapper}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={{ ...styles.th, textTransform: "none" as const }}>Name</th>
              <th style={{ ...styles.th, textTransform: "none" as const }}>Status</th>
              <th style={{ ...styles.th, textTransform: "none" as const }}>Records</th>
              {allMetricKeys.map((k) => (
                <th key={k} style={{ ...styles.th, textTransform: "none" as const, textAlign: "right" as const }}>
                  {formatMetricName(k).replace(/ \(avg\)$/, "").replace(/ Mean$/, "")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {models.map((model) => (
              <tr
                key={model.model_name}
                onClick={() => setDrillDownModel(model)}
                style={{ cursor: "pointer" }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "var(--color-background-secondary)"; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = ""; }}
              >
                <td style={{ ...styles.td, textAlign: "left", color: "var(--color-accent)", fontWeight: 500, fontFamily: "var(--font-sans)", padding: "8px 12px" }}>
                  {model.model_display_name || model.model_name}
                </td>
                <td style={{ ...styles.td, textAlign: "left", fontFamily: "var(--font-sans)", padding: "8px 12px" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", color: "var(--color-success, #a0d89f)", fontWeight: 600 }}>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M2 8a6 6 0 1 1 12 0A6 6 0 0 1 2 8Zm6-7a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm2.85 5.85a.5.5 0 0 0-.7-.7l-2.9 2.9-1.4-1.4a.5.5 0 1 0-.7.7L6.9 10.1c.2.2.5.2.7 0l3.25-3.25Z"/></svg>
                    Completed
                  </span>
                </td>
                <td style={{ ...styles.td, textAlign: "center", padding: "8px 12px" }}>
                  {model.summary.aggregated_evaluators.number_of_records || model.records.length}
                </td>
                {allMetricKeys.map((k) => {
                  const display = formatEvaluatorAsPassRate(model, k);
                  return (
                    <td key={k} style={{ ...styles.td, textAlign: "left", padding: "4px 6px" }}>
                      {display ? (
                        <div style={{
                          background: display.allPassed
                            ? "#20291F"
                            : "rgba(209, 52, 56, 0.15)",
                          borderRadius: "6px",
                          padding: "4px 12px",
                          minWidth: "70px",
                        }}>
                          <div style={{ color: "#FFFFFF", fontWeight: 600, fontSize: "14px", textAlign: "left", lineHeight: "1.2" }}>{display.pct}</div>
                          {display.detail && (
                            <div style={{
                              fontSize: "12px",
                              color: display.allPassed
                                ? "var(--color-success, #a0d89f)"
                                : "var(--color-error, #e74856)",
                              marginTop: "0px",
                              textAlign: "left",
                              lineHeight: "1.2",
                            }}>
                              {display.detail}
                            </div>
                          )}
                        </div>
                      ) : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </>
      )}

      {/* Evaluators section */}
      {evaluators.length > 0 && (
        <div style={{ marginTop: "32px" }}>
          <h2 style={{ fontSize: "16px", fontWeight: 600, margin: "0 0 4px" }}>Evaluators</h2>
          <p style={{ fontSize: "13px", color: "var(--color-text-muted, var(--color-text-secondary))", margin: "0 0 12px" }}>
            Evaluators stay consistent across all runs in this group. To use different evaluators, exit this group and start a new evaluation.
          </p>
          <div style={styles.tableWrapper}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={{ ...styles.th, textTransform: "none" as const }}>Name</th>
                  <th style={{ ...styles.th, textTransform: "none" as const }}>Type</th>
                </tr>
              </thead>
              <tbody>
                {evaluators.map((ev) => (
                  <tr key={ev.rawName}>
                    <td style={{ ...styles.td, textAlign: "left", fontWeight: 500, fontFamily: "var(--font-sans)" }}>{ev.rawName}</td>
                    <td style={{ ...styles.td, textAlign: "left", fontFamily: "var(--font-sans)", color: "var(--color-text-secondary)" }}>{ev.type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Dataset section */}
      {datasetRecords.length > 0 && (
        <div style={{ marginTop: "32px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <div>
              <h2 style={{ fontSize: "16px", fontWeight: 600, margin: "0 0 4px" }}>Dataset</h2>
              <p style={{ fontSize: "13px", color: "var(--color-text-muted, var(--color-text-secondary))", margin: 0 }}>
                {datasetName} · {datasetRecords.length} record{datasetRecords.length !== 1 ? "s" : ""}
              </p>
            </div>
            <button
              onClick={() => setDatasetExpanded(!datasetExpanded)}
              style={{
                ...styles.buttonSmall,
                ...(datasetExpanded ? styles.buttonSmallActive : {}),
              }}
            >
              {datasetExpanded ? "Hide Dataset" : "View Dataset"}
            </button>
          </div>

          {datasetExpanded && (
            <>
              <div style={styles.tableWrapper}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={{ ...styles.th, textTransform: "none" as const, textAlign: "center" as const, width: "50px" }}>#</th>
                      {datasetColumns.map((col) => (
                        <th key={col} style={{ ...styles.th, textTransform: "none" as const, textAlign: "left" as const }}>
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedDatasetRecords.map((rec, idx) => {
                      const globalIdx = (datasetPage - 1) * datasetPageSize + idx;
                      return (
                        <tr key={globalIdx}>
                          <td style={{ ...styles.td, textAlign: "center", color: "var(--color-text-muted, var(--color-text-secondary))", fontSize: "12px" }}>
                            {globalIdx + 1}
                          </td>
                          {datasetColumns.map((col) => {
                            const val = rec[col];
                            const displayVal = val == null ? "—" : typeof val === "object" ? JSON.stringify(val) : String(val);
                            return (
                              <td
                                key={col}
                                title={displayVal}
                                style={{
                                  ...styles.td,
                                  textAlign: "left",
                                  fontFamily: "var(--font-sans)",
                                  maxWidth: "300px",
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                {displayVal}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Dataset pagination */}
              {datasetTotalPages > 1 && (
                <div style={{ ...styles.pagination, padding: "12px 0" }}>
                  <button
                    style={{ ...styles.pageButton, ...(datasetPage === 1 ? styles.pageButtonDisabled : {}) }}
                    onClick={() => setDatasetPage((p) => Math.max(1, p - 1))}
                    disabled={datasetPage === 1}
                  >
                    ‹ Prev
                  </button>
                  <span style={styles.pageInfo}>Page {datasetPage} of {datasetTotalPages}</span>
                  <select
                    value={datasetPageSize}
                    onChange={(e) => setDatasetPageSize(Number(e.target.value))}
                    style={styles.pageSizeSelect}
                  >
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>{size} / page</option>
                    ))}
                  </select>
                  <button
                    style={{ ...styles.pageButton, ...(datasetPage === datasetTotalPages ? styles.pageButtonDisabled : {}) }}
                    onClick={() => setDatasetPage((p) => Math.min(datasetTotalPages, p + 1))}
                    disabled={datasetPage === datasetTotalPages}
                  >
                    Next ›
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Prev/Next */}
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "8px", marginTop: "16px", fontSize: "13px", color: "var(--color-text-muted, var(--color-text-secondary))" }}>
        ‹ Prev &nbsp; Next ›
      </div>
    </div>
  );
}

// ---- Dataset Viewer Page ----

function DatasetViewer({
  data,
  onBack,
}: {
  data: ViewResultsData;
  onBack: () => void;
}) {
  const [search, setSearch] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const models = Array.isArray(data.models) ? data.models : [];

  const datasetName = useMemo(() => {
    const path = data.output_path || "";
    const parts = path.split("/");
    return parts.length > 1 ? parts[parts.length - 2] : parts[0] || "Dataset";
  }, [data.output_path]);

  const allRecords = useMemo(() => {
    if (models.length === 0) return [];
    return models[0].records.map((r) => r.record);
  }, [models]);

  const columns = useMemo(() => {
    const keys = new Set<string>();
    for (const rec of allRecords) {
      for (const k of Object.keys(rec)) keys.add(k);
    }
    return Array.from(keys);
  }, [allRecords]);

  const filtered = useMemo(() => {
    if (!search.trim()) return allRecords;
    const q = search.toLowerCase();
    return allRecords.filter((rec) =>
      Object.values(rec).some((v) =>
        v != null && String(v).toLowerCase().includes(q)
      )
    );
  }, [allRecords, search]);

  const totalPages = Math.ceil(filtered.length / pageSize);
  const paginated = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, currentPage, pageSize]);

  useEffect(() => {
    setCurrentPage(1);
  }, [search, pageSize]);

  return (
    <div>
      {/* Back button */}
      <div style={{ marginBottom: "16px" }}>
        <button
          onClick={onBack}
          style={{
            background: "none",
            border: "none",
            color: "var(--color-text-secondary)",
            cursor: "pointer",
            fontSize: "13px",
            padding: "4px 0",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontFamily: "var(--font-sans)",
          }}
        >
          <span style={{ fontSize: "16px" }}>←</span> Back to evaluations
        </button>
      </div>

      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <h1 style={{ fontSize: "20px", fontWeight: 600, margin: "0 0 4px", color: "#FFFFFF" }}>
          {datasetName}
        </h1>
        <p style={{ fontSize: "14px", color: "var(--color-text-muted, var(--color-text-secondary))", margin: 0 }}>
          {allRecords.length} record{allRecords.length !== 1 ? "s" : ""}
          {filtered.length !== allRecords.length && ` · ${filtered.length} matching`}
        </p>
      </div>

      {/* Search bar */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "20px", alignItems: "center" }}>
        <div style={{ position: "relative", flex: 1 }}>
          <span style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--color-text-muted, var(--color-text-secondary))", pointerEvents: "none" }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M11.5 11.5L14 14" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/><circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.2"/></svg>
          </span>
          <input
            type="text"
            placeholder="Search dataset records..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              ...styles.searchInput,
              flex: "unset",
              width: "100%",
              paddingLeft: "36px",
              background: "#141414",
            }}
          />
        </div>
      </div>

      {/* Dataset table */}
      <div style={styles.tableWrapper}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={{ ...styles.th, textTransform: "none" as const, textAlign: "center" as const, width: "50px", color: "#FFFFFF" }}>#</th>
              {columns.map((col) => (
                <th key={col} style={{ ...styles.th, textTransform: "none" as const, textAlign: "left" as const, color: "#FFFFFF" }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginated.map((rec, idx) => {
              const globalIdx = (currentPage - 1) * pageSize + idx;
              return (
                <tr key={globalIdx}>
                  <td style={{ ...styles.td, textAlign: "center", color: "var(--color-text-muted, var(--color-text-secondary))", fontSize: "12px" }}>
                    {globalIdx + 1}
                  </td>
                  {columns.map((col) => {
                    const val = rec[col];
                    const displayVal = val == null ? "—" : typeof val === "object" ? JSON.stringify(val) : String(val);
                    return (
                      <td
                        key={col}
                        title={displayVal}
                        style={{
                          ...styles.td,
                          textAlign: "left",
                          fontFamily: "var(--font-sans)",
                          color: "#FFFFFF",
                          maxWidth: "300px",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {displayVal}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {filtered.length === 0 && (
        <div style={{ textAlign: "center", padding: "40px", color: "var(--color-text-muted, var(--color-text-secondary))" }}>
          {search ? "No records match your search." : "No records found."}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ ...styles.pagination, padding: "12px 0" }}>
          <button
            style={{ ...styles.pageButton, ...(currentPage === 1 ? styles.pageButtonDisabled : {}) }}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
          >
            ‹ Prev
          </button>
          <span style={styles.pageInfo}>Page {currentPage} of {totalPages}</span>
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            style={styles.pageSizeSelect}
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>{size} / page</option>
            ))}
          </select>
          <button
            style={{ ...styles.pageButton, ...(currentPage === totalPages ? styles.pageButtonDisabled : {}) }}
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
          >
            Next ›
          </button>
        </div>
      )}
    </div>
  );
}

/** Standalone mode: data is pre-injected via CLI, supports switching experiments. */
function StandaloneResultsViewer({ initialData }: { initialData: ViewResultsData }) {
  const [data, setData] = useState<ViewResultsData>(initialData);
  const [experiments, setExperiments] = useState<ExperimentListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [experimentsFetched, setExperimentsFetched] = useState(false);
  // Navigation: null = overview, "detail" = experiment detail, "compare" = comparison table
  const [selectedExperiment, setSelectedExperiment] = useState<string | null>(null);
  const [showCompare, setShowCompare] = useState(false);
  const [showDataset, setShowDataset] = useState(false);

  const currentExperiment = (data.output_path || "").split("/").pop() || "";

  useEffect(() => {
    fetch("api/experiments")
      .then((res) => {
        if (!res.ok) throw new Error("API error");
        return res.json();
      })
      .then((list: ExperimentListItem[]) => {
        if (Array.isArray(list) && list.length > 0) {
          setExperiments(list);
          setExperimentsFetched(true);
        } else {
          // Empty or invalid response — go directly to detail
          setExperimentsFetched(true);
          setSelectedExperiment(currentExperiment);
        }
      })
      .catch(() => {
        // If API fails (no server, single-file mode), show detail view directly
        setExperimentsFetched(true);
        setSelectedExperiment(currentExperiment);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadExperiment = useCallback(
    async (name: string) => {
      setSelectedExperiment(name);
      setShowCompare(false);
      setShowDataset(false);
      if (name === currentExperiment) return;
      setLoading(true);
      try {
        const res = await fetch(`api/results/${encodeURIComponent(name)}`);
        const result = await res.json();
        if (result.data) {
          setData(result.data);
        } else if (result.summary) {
          setData(result);
        }
      } catch (e) {
        console.error("Failed to load experiment:", e);
      } finally {
        setLoading(false);
      }
    },
    [currentExperiment]
  );

  const goBackToOverview = useCallback(() => {
    setSelectedExperiment(null);
    setShowCompare(false);
    setShowDataset(false);
    // If we don't have experiments yet, retry the fetch
    if (experiments.length === 0) {
      setExperimentsFetched(false);
      fetch("api/experiments")
        .then((res) => {
          if (!res.ok) throw new Error("API error");
          return res.json();
        })
        .then((list: ExperimentListItem[]) => {
          if (Array.isArray(list) && list.length > 0) {
            setExperiments(list);
          }
          setExperimentsFetched(true);
        })
        .catch(() => {
          setExperimentsFetched(true);
        });
    }
  }, [experiments.length]);

  const goBackToDetail = useCallback(() => {
    setShowCompare(false);
    setShowDataset(false);
  }, []);

  const viewDataset = useCallback(
    async (experimentName: string) => {
      setShowDataset(true);
      setShowCompare(false);
      setSelectedExperiment(experimentName);
      if (experimentName === currentExperiment) return;
      setLoading(true);
      try {
        const res = await fetch(`api/results/${encodeURIComponent(experimentName)}`);
        const result = await res.json();
        if (result.data) {
          setData(result.data);
        } else if (result.summary) {
          setData(result);
        }
      } catch (e) {
        console.error("Failed to load experiment:", e);
      } finally {
        setLoading(false);
      }
    },
    [currentExperiment]
  );

  // Loading experiments list
  if (!experimentsFetched) {
    return (
      <main style={styles.main}>
        <div style={{ ...styles.loading, padding: "60px" }}>Loading evaluations...</div>
      </main>
    );
  }

  // Page 1: Evaluations overview list (or when navigating back)
  if (!selectedExperiment) {
    if (experiments.length > 0) {
      return (
        <main style={styles.main}>
          <ExperimentsOverview experiments={experiments} onSelect={loadExperiment} onViewDataset={viewDataset} />
        </main>
      );
    }
    // No experiments available — show current experiment detail directly
    return (
      <main style={styles.main}>
        {loading ? (
          <div style={{ ...styles.loading, padding: "60px" }}>Loading...</div>
        ) : (
          <ExperimentDetail
            data={data}
            onCompare={() => setShowCompare(true)}
          />
        )}
      </main>
    );
  }

  // Dataset viewer page
  if (showDataset) {
    return (
      <main style={styles.main}>
        {loading ? (
          <div style={{ ...styles.loading, padding: "60px" }}>Loading...</div>
        ) : (
          <DatasetViewer data={data} onBack={goBackToOverview} />
        )}
      </main>
    );
  }

  // Page 3: Comparison table
  if (showCompare) {
    return (
      <main style={styles.main}>
        <div style={{ marginBottom: "16px" }}>
          <button
            onClick={goBackToDetail}
            style={{
              background: "none",
              border: "none",
              color: "var(--color-text-secondary)",
              cursor: "pointer",
              fontSize: "13px",
              padding: "4px 0",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontFamily: "var(--font-sans)",
            }}
          >
            <span style={{ fontSize: "16px" }}>←</span> {currentExperiment}
          </button>
        </div>
        {loading ? (
          <div style={{ ...styles.loading, padding: "60px" }}>Loading...</div>
        ) : (
          <ComparisonTable data={data} />
        )}
      </main>
    );
  }

  // Page 2: Experiment detail (Foundry-style runs table)
  return (
    <main style={styles.main}>
      {loading ? (
        <div style={{ ...styles.loading, padding: "60px" }}>Loading...</div>
      ) : (
        <ExperimentDetail
          data={data}
          onBack={goBackToOverview}
          onCompare={() => setShowCompare(true)}
        />
      )}
    </main>
  );
}

/** MCP mode: connects to MCP server for data and refresh. */
function McpResultsViewerApp() {
  const [resultsData, setResultsData] = useState<ViewResultsData | null>(null);
  const [hostContext, setHostContext] = useState<McpUiHostContext | undefined>();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { app, error } = useApp({
    appInfo: { name: "Evee Results Viewer", version: "1.0.0" },
    capabilities: {},
    onAppCreated: (app) => {
      app.onteardown = async () => {
        console.info("App is being torn down");
        return {};
      };

      app.ontoolinput = async (input) => {
        console.info("Received tool call input:", input);
      };

      app.ontoolresult = async (result) => {
        console.info("Received tool call result:", result);
        const data = extractResultsData(result);
        if (data) {
          setResultsData(data);
          setErrorMsg(null);
        } else {
          setErrorMsg("Failed to parse results data");
        }
      };

      app.ontoolcancelled = (params) => {
        console.info("Tool call cancelled:", params.reason);
        setErrorMsg(`Tool cancelled: ${params.reason}`);
      };

      app.onerror = (err) => {
        console.error("App error:", err);
        setErrorMsg(String(err));
      };

      app.onhostcontextchanged = (params) => {
        setHostContext((prev) => ({ ...prev, ...params }));
      };
    },
  });

  useHostStyles(app);

  useEffect(() => {
    if (app) {
      setHostContext(app.getHostContext());
    }
  }, [app]);

  const handleRefresh = useCallback(async () => {
    if (!app || !resultsData) return;

    try {
      console.info("Refreshing results...");
      const result = await app.callServerTool({
        name: "view_results",
        arguments: { output_path: resultsData.output_path },
      });
      const data = extractResultsData(result);
      if (data) {
        setResultsData(data);
        setErrorMsg(null);
      }
    } catch (e) {
      console.error("Refresh failed:", e);
      setErrorMsg("Failed to refresh results");
    }
  }, [app, resultsData]);

  if (error) {
    return (
      <div style={styles.main}>
        <div style={styles.error}>
          <strong>Connection Error:</strong> {error.message}
        </div>
      </div>
    );
  }

  if (!app) {
    return <div style={styles.loading}>Connecting to MCP server...</div>;
  }

  return (
    <main
      style={{
        ...styles.main,
        paddingTop: hostContext?.safeAreaInsets?.top ?? 16,
        paddingRight: hostContext?.safeAreaInsets?.right ?? 16,
        paddingBottom: hostContext?.safeAreaInsets?.bottom ?? 16,
        paddingLeft: hostContext?.safeAreaInsets?.left ?? 16,
      }}
    >
      {errorMsg && (
        <div style={styles.error}>
          <strong>Error:</strong> {errorMsg}
        </div>
      )}

      {resultsData ? (
        <ComparisonTable data={resultsData} onRefresh={handleRefresh} />
      ) : (
        <div style={{ ...styles.loading, flexDirection: "column", gap: "20px" }}>
          <img src={EVEE_LOGO} alt="Evee" style={{ height: "48px", opacity: 0.7 }} />
          <div style={{ fontSize: "14px" }}>Waiting for evaluation results...</div>
        </div>
      )}
    </main>
  );
}

/** Friendly empty state shown when there is no experiment data. */
function EmptyStateMessage() {
  return (
    <main style={styles.main}>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "60vh",
          gap: "20px",
          textAlign: "center",
          padding: "40px 20px",
        }}
      >
        <img src={EVEE_LOGO} alt="Evee" style={{ height: "48px", opacity: 0.7 }} />
        <h2
          style={{
            fontSize: "18px",
            fontWeight: 600,
            color: "var(--color-text-primary)",
            margin: 0,
          }}
        >
          No evaluation results yet
        </h2>
        <p
          style={{
            fontSize: "14px",
            color: "var(--color-text-muted, var(--color-text-secondary))",
            margin: 0,
            maxWidth: "420px",
            lineHeight: 1.6,
          }}
        >
          Run an evaluation to see results here.
        </p>
      </div>
    </main>
  );
}

/** Route to standalone or MCP mode based on whether data is pre-injected. */
function ResultsViewerApp() {
  if (window.__EVEE_RESULTS_DATA__) {
    return <StandaloneResultsViewer initialData={window.__EVEE_RESULTS_DATA__} />;
  }
  // If opened directly without MCP or injected data, show a friendly empty state
  // instead of hanging on "Connecting to MCP server..."
  if (typeof window.__EVEE_RESULTS_DATA__ === "undefined" && !window.location.search.includes("mcp")) {
    return <EmptyStateMessage />;
  }
  return <McpResultsViewerApp />;
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element not found. Ensure HTML contains <div id='root'></div>");
}

createRoot(rootElement).render(
  <StrictMode>
    <ResultsViewerApp />
  </StrictMode>
);
