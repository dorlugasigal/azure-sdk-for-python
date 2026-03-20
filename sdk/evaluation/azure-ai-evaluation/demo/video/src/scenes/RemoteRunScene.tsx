import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { COLORS, FONTS } from "../styles";
import { Terminal } from "../components/Terminal";
import { REMOTE_RUN_LINES } from "../data/terminalOutput";

export const RemoteRunScene: React.FC = () => {
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
          ☁️ Running Remote Evaluation
        </div>
        <div
          style={{
            fontSize: 14,
            fontFamily: FONTS.mono,
            color: COLORS.accentPurple,
            opacity: headerOpacity,
            backgroundColor: `${COLORS.accentPurple}20`,
            padding: "4px 12px",
            borderRadius: 12,
          }}
        >
          10 rows • Azure AI Foundry
        </div>
      </div>
      <Terminal lines={REMOTE_RUN_LINES} typingSpeed={10} title="Terminal — local-evals --remote" />
    </AbsoluteFill>
  );
};
