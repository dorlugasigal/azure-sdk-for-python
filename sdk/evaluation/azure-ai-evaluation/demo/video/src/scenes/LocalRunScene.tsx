import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { COLORS, FONTS } from "../styles";
import { Terminal } from "../components/Terminal";
import { LOCAL_RUN_LINES } from "../data/terminalOutput";

export const LocalRunScene: React.FC = () => {
  const frame = useCurrentFrame();
  const headerOpacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "40px 80px",
        gap: 20,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          style={{
            fontSize: 28,
            fontFamily: FONTS.sans,
            fontWeight: 600,
            color: COLORS.text,
            opacity: headerOpacity,
          }}
        >
          🚀 Running Local Evaluation
        </div>
        <div
          style={{
            fontSize: 14,
            fontFamily: FONTS.mono,
            color: COLORS.accentGreen,
            opacity: headerOpacity,
            backgroundColor: `${COLORS.accentGreen}20`,
            padding: "4px 12px",
            borderRadius: 12,
          }}
        >
          3 rows • small dataset
        </div>
      </div>
      <Terminal lines={LOCAL_RUN_LINES} typingSpeed={12} title="Terminal — local-evals" />
    </AbsoluteFill>
  );
};
