import React from "react";
import { AbsoluteFill, useCurrentFrame, spring, interpolate } from "remotion";
import { COLORS, FONTS, FPS } from "../styles";

export const TitleScene: React.FC = () => {
  const frame = useCurrentFrame();
  const titleY = spring({ frame, fps: FPS, from: 30, to: 0, config: { damping: 15 } });
  const titleOpacity = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const subtitleOpacity = interpolate(frame, [15, 35], [0, 1], { extrapolateRight: "clamp" });
  const badgeOpacity = interpolate(frame, [30, 50], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at 50% 40%, #1a2332 0%, ${COLORS.bg} 70%)`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
      }}
    >
      <div
        style={{
          fontSize: 64,
          fontFamily: FONTS.sans,
          fontWeight: 700,
          color: COLORS.text,
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          textAlign: "center",
        }}
      >
        Evaluating Question Answering
      </div>
      <div
        style={{
          fontSize: 36,
          fontFamily: FONTS.sans,
          fontWeight: 500,
          color: COLORS.accent,
          opacity: subtitleOpacity,
          textAlign: "center",
        }}
      >
        with Azure AI Evaluation
      </div>
      <div
        style={{
          marginTop: 20,
          fontSize: 18,
          fontFamily: FONTS.mono,
          color: COLORS.textMuted,
          opacity: badgeOpacity,
          backgroundColor: COLORS.bgLight,
          padding: "8px 20px",
          borderRadius: 20,
          border: `1px solid ${COLORS.border}`,
        }}
      >
        local-evals CLI
      </div>
    </AbsoluteFill>
  );
};
