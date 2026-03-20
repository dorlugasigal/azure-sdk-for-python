import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate, spring } from "remotion";
import { COLORS, FONTS, FPS } from "../styles";
import { Terminal } from "../components/Terminal";
import { Browser } from "../components/Browser";
import { VIEW_COMMAND } from "../data/terminalOutput";

const DashboardContent: React.FC = () => {
  const frame = useCurrentFrame();

  const metrics = [
    { model: "gpt-4.1-mini", temp: "0.3", relevance: 4.2, coherence: 4.5, conciseness: 0.87 },
    { model: "gpt-4.1-mini", temp: "0.9", relevance: 3.8, coherence: 4.1, conciseness: 0.72 },
    { model: "gpt-4.1", temp: "0.3", relevance: 4.7, coherence: 4.8, conciseness: 0.91 },
    { model: "gpt-4.1", temp: "0.9", relevance: 4.3, coherence: 4.4, conciseness: 0.68 },
  ];

  return (
    <div style={{ padding: "24px 32px", fontFamily: FONTS.sans }}>
      <div style={{ fontSize: 20, fontWeight: 700, color: "#1a1a2e", marginBottom: 4 }}>
        Model Comparison Dashboard
      </div>
      <div style={{ fontSize: 13, color: "#666", marginBottom: 20 }}>
        Experiment: model-comparison • 3 rows • 4 variants
      </div>
      
      {/* Metric cards */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
        {[
          { label: "Best Model", value: "gpt-4.1", sub: "@ temp=0.3", color: "#0078d4" },
          { label: "Avg Relevance", value: "4.25", sub: "across variants", color: "#107c10" },
          { label: "Avg Coherence", value: "4.45", sub: "across variants", color: "#5c2d91" },
          { label: "Avg Conciseness", value: "0.80", sub: "custom metric", color: "#d83b01" },
        ].map((card, i) => {
          const cardScale = spring({ frame: frame - i * 5, fps: FPS, from: 0.9, to: 1, config: { damping: 12 } });
          const cardOpacity = interpolate(frame - i * 5, [0, 15], [0, 1], { extrapolateRight: "clamp" });
          return (
            <div key={i} style={{ flex: 1, backgroundColor: "#f8f9fa", borderRadius: 8, padding: "16px", borderLeft: `4px solid ${card.color}`, transform: `scale(${cardScale})`, opacity: cardOpacity }}>
              <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>{card.label}</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: card.color }}>{card.value}</div>
              <div style={{ fontSize: 11, color: "#999" }}>{card.sub}</div>
            </div>
          );
        })}
      </div>

      {/* Simple bar chart */}
      <div style={{ backgroundColor: "#f8f9fa", borderRadius: 8, padding: "20px" }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: "#333", marginBottom: 16 }}>Metrics by Variant</div>
        {metrics.map((m, i) => {
          const barDelay = 30 + i * 8;
          const barWidth = spring({ frame: frame - barDelay, fps: FPS, from: 0, to: 1, config: { damping: 12 } });
          return (
            <div key={i} style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: 140, fontSize: 12, color: "#555", fontFamily: FONTS.mono }}>
                {m.model} t={m.temp}
              </div>
              <div style={{ flex: 1, display: "flex", gap: 4, height: 20 }}>
                <div style={{ width: `${(m.relevance / 5) * 100 * barWidth}%`, backgroundColor: "#107c10", borderRadius: 3, transition: "width 0.3s" }} />
                <div style={{ width: `${(m.coherence / 5) * 100 * barWidth}%`, backgroundColor: "#5c2d91", borderRadius: 3, transition: "width 0.3s" }} />
                <div style={{ width: `${m.conciseness * 100 * barWidth}%`, backgroundColor: "#d83b01", borderRadius: 3, transition: "width 0.3s" }} />
              </div>
            </div>
          );
        })}
        <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 11, color: "#888" }}>
          <span>🟢 Relevance</span>
          <span>🟣 Coherence</span>
          <span>🟠 Conciseness</span>
        </div>
      </div>
    </div>
  );
};

export const BrowserViewScene: React.FC = () => {
  const frame = useCurrentFrame();
  const showTerminal = frame < 80;
  const showBrowser = frame >= 60;
  
  const terminalOpacity = interpolate(frame, [60, 80], [1, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const browserOpacity = interpolate(frame, [60, 85], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      {showTerminal && (
        <AbsoluteFill style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "40px 80px", opacity: terminalOpacity }}>
          <Terminal lines={VIEW_COMMAND} typingSpeed={12} title="Terminal — local-evals" />
        </AbsoluteFill>
      )}
      {showBrowser && (
        <AbsoluteFill style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "20px 60px", opacity: browserOpacity }}>
          <Browser url="http://localhost:5173/dashboard">
            <DashboardContent />
          </Browser>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
