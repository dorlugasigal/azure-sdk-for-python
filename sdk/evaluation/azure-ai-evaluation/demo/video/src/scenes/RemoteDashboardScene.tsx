import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate, spring } from "remotion";
import { COLORS, FONTS, FPS } from "../styles";
import { Browser } from "../components/Browser";

const FoundryDashboard: React.FC = () => {
  const frame = useCurrentFrame();

  const runs = [
    { model: "gpt-4.1-mini", temp: 0.3, relevance: 4.3, coherence: 4.6, conciseness: 0.85, status: "completed" },
    { model: "gpt-4.1-mini", temp: 0.9, relevance: 3.9, coherence: 4.2, conciseness: 0.71, status: "completed" },
    { model: "gpt-4.1", temp: 0.3, relevance: 4.8, coherence: 4.9, conciseness: 0.92, status: "completed" },
    { model: "gpt-4.1", temp: 0.9, relevance: 4.4, coherence: 4.5, conciseness: 0.69, status: "completed" },
  ];

  return (
    <div style={{ fontFamily: FONTS.sans }}>
      {/* Foundry header */}
      <div style={{ backgroundColor: "#0078d4", padding: "12px 24px", display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ color: "#fff", fontSize: 15, fontWeight: 600 }}>Azure AI Foundry</span>
        <span style={{ color: "rgba(255,255,255,0.7)", fontSize: 13 }}>/ Evaluations / model-comparison</span>
      </div>
      
      <div style={{ padding: "20px 24px" }}>
        {/* Summary row */}
        <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
          {[
            { label: "Total Runs", value: "4", icon: "🔄" },
            { label: "Dataset Rows", value: "10", icon: "📊" },
            { label: "Metrics", value: "3", icon: "📐" },
            { label: "Duration", value: "1m 23s", icon: "⏱️" },
          ].map((item, i) => {
            const cardOpacity = interpolate(frame - i * 6, [0, 15], [0, 1], { extrapolateRight: "clamp" });
            return (
              <div key={i} style={{ flex: 1, backgroundColor: "#f3f2f1", borderRadius: 6, padding: "12px 16px", opacity: cardOpacity }}>
                <div style={{ fontSize: 12, color: "#605e5c" }}>{item.icon} {item.label}</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: "#323130" }}>{item.value}</div>
              </div>
            );
          })}
        </div>

        {/* Results table */}
        <div style={{ borderRadius: 6, border: "1px solid #edebe9", overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ backgroundColor: "#f3f2f1" }}>
                <th style={{ padding: "10px 16px", textAlign: "left", color: "#323130", fontWeight: 600 }}>Model</th>
                <th style={{ padding: "10px 16px", textAlign: "center", color: "#323130", fontWeight: 600 }}>Temp</th>
                <th style={{ padding: "10px 16px", textAlign: "center", color: "#323130", fontWeight: 600 }}>Relevance</th>
                <th style={{ padding: "10px 16px", textAlign: "center", color: "#323130", fontWeight: 600 }}>Coherence</th>
                <th style={{ padding: "10px 16px", textAlign: "center", color: "#323130", fontWeight: 600 }}>Conciseness</th>
                <th style={{ padding: "10px 16px", textAlign: "center", color: "#323130", fontWeight: 600 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run, i) => {
                const rowOpacity = interpolate(frame - 30 - i * 8, [0, 12], [0, 1], { extrapolateRight: "clamp" });
                const isBest = run.model === "gpt-4.1" && run.temp === 0.3;
                return (
                  <tr key={i} style={{ borderTop: "1px solid #edebe9", backgroundColor: isBest ? "#f0f9ff" : "#fff", opacity: rowOpacity }}>
                    <td style={{ padding: "10px 16px", fontWeight: isBest ? 600 : 400, color: "#323130" }}>
                      {run.model} {isBest && "⭐"}
                    </td>
                    <td style={{ padding: "10px 16px", textAlign: "center", color: "#605e5c" }}>{run.temp}</td>
                    <td style={{ padding: "10px 16px", textAlign: "center", color: run.relevance >= 4.5 ? "#107c10" : "#323130" }}>{run.relevance.toFixed(1)}</td>
                    <td style={{ padding: "10px 16px", textAlign: "center", color: run.coherence >= 4.5 ? "#107c10" : "#323130" }}>{run.coherence.toFixed(1)}</td>
                    <td style={{ padding: "10px 16px", textAlign: "center", color: run.conciseness >= 0.85 ? "#107c10" : "#323130" }}>{run.conciseness.toFixed(2)}</td>
                    <td style={{ padding: "10px 16px", textAlign: "center" }}>
                      <span style={{ backgroundColor: "#dff6dd", color: "#107c10", padding: "2px 8px", borderRadius: 4, fontSize: 12 }}>
                        ✓ {run.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Insight */}
        <div style={{ marginTop: 16, padding: "12px 16px", backgroundColor: "#f0f9ff", borderRadius: 6, borderLeft: "4px solid #0078d4", opacity: interpolate(frame, [80, 100], [0, 1], { extrapolateRight: "clamp" }) }}>
          <div style={{ fontSize: 13, color: "#0078d4", fontWeight: 600 }}>💡 Insight</div>
          <div style={{ fontSize: 12, color: "#323130", marginTop: 4 }}>
            gpt-4.1 at temperature 0.3 consistently outperforms across all metrics. Lower temperature improves conciseness by ~30%.
          </div>
        </div>
      </div>
    </div>
  );
};

export const RemoteDashboardScene: React.FC = () => {
  const frame = useCurrentFrame();
  const headerOpacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "20px 60px",
        gap: 16,
      }}
    >
      <div
        style={{
          fontSize: 28,
          fontFamily: FONTS.sans,
          fontWeight: 600,
          color: COLORS.text,
          opacity: headerOpacity,
          paddingLeft: 20,
        }}
      >
        🌐 Azure AI Foundry — Evaluation Results
      </div>
      <Browser url="https://ai.azure.com/evaluations/model-comparison-20260319">
        <FoundryDashboard />
      </Browser>
    </AbsoluteFill>
  );
};
