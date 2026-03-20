import React from "react";
import { AbsoluteFill, useCurrentFrame, spring, interpolate } from "remotion";
import { COLORS, FONTS, FPS } from "../styles";

export const TransitionScene: React.FC = () => {
  const frame = useCurrentFrame();
  const scale = spring({ frame, fps: FPS, from: 0.8, to: 1, config: { damping: 12 } });
  const opacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const subtitleOpacity = interpolate(frame, [20, 40], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at 50% 50%, #1a2332 0%, ${COLORS.bg} 70%)`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 20,
      }}
    >
      <div
        style={{
          fontSize: 56,
          fontFamily: FONTS.sans,
          fontWeight: 700,
          color: COLORS.accentGreen,
          opacity,
          transform: `scale(${scale})`,
        }}
      >
        Sounds good! 🎉
      </div>
      <div
        style={{
          fontSize: 24,
          fontFamily: FONTS.sans,
          fontWeight: 400,
          color: COLORS.textMuted,
          opacity: subtitleOpacity,
        }}
      >
        Let's scale up with --remote
      </div>
    </AbsoluteFill>
  );
};
