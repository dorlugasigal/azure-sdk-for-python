import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { COLORS, FONTS } from "../styles";
import { Terminal } from "../components/Terminal";
import { LOCAL_RESULTS_TABLE } from "../data/terminalOutput";

export const LocalResultsScene: React.FC = () => {
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
      <div
        style={{
          fontSize: 28,
          fontFamily: FONTS.sans,
          fontWeight: 600,
          color: COLORS.text,
          opacity: headerOpacity,
        }}
      >
        📊 Evaluation Results
      </div>
      <Terminal lines={LOCAL_RESULTS_TABLE} typingSpeed={10} title="Terminal — Results" />
    </AbsoluteFill>
  );
};
