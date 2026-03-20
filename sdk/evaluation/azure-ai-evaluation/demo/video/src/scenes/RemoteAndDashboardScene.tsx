import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, interpolate } from "remotion";
import { COLORS, FONTS } from "../styles";

export const RemoteAndDashboardScene: React.FC = () => {
  const frame = useCurrentFrame();
  const labelOpacity = interpolate(frame, [0, 20, 40, 60], [0, 1, 1, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      <OffthreadVideo
        src={staticFile("remote.mp4")}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
        }}
      />
      {/* Intro label overlay */}
      <div
        style={{
          position: "absolute",
          top: 30,
          left: 40,
          opacity: labelOpacity,
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <div
          style={{
            fontSize: 22,
            fontFamily: FONTS.sans,
            fontWeight: 600,
            color: COLORS.text,
            backgroundColor: "rgba(0,0,0,0.7)",
            padding: "8px 18px",
            borderRadius: 8,
            backdropFilter: "blur(8px)",
          }}
        >
          ☁️ Remote Evaluation &amp; Foundry Dashboard
        </div>
        <div
          style={{
            fontSize: 14,
            fontFamily: FONTS.mono,
            color: COLORS.accentPurple,
            backgroundColor: "rgba(0,0,0,0.7)",
            padding: "6px 14px",
            borderRadius: 12,
            backdropFilter: "blur(8px)",
          }}
        >
          live recording
        </div>
      </div>
    </AbsoluteFill>
  );
};
