import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { COLORS, FONTS } from "../styles";
import { CodeBlock } from "../components/CodeBlock";
import { CUSTOM_METRIC_CODE } from "../data/yamlContent";

export const CustomMetricScene: React.FC = () => {
  const frame = useCurrentFrame();
  const headerOpacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const badgeOpacity = interpolate(frame, [20, 40], [0, 1], { extrapolateRight: "clamp" });

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
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div
          style={{
            fontSize: 28,
            fontFamily: FONTS.sans,
            fontWeight: 600,
            color: COLORS.text,
            opacity: headerOpacity,
          }}
        >
          🎯 Custom Metric: Conciseness
        </div>
        <div
          style={{
            fontSize: 14,
            fontFamily: FONTS.mono,
            color: COLORS.accentOrange,
            opacity: badgeOpacity,
            backgroundColor: `${COLORS.accentOrange}20`,
            padding: "4px 12px",
            borderRadius: 12,
            border: `1px solid ${COLORS.accentOrange}40`,
          }}
        >
          @metric decorator
        </div>
      </div>
      <CodeBlock
        code={CUSTOM_METRIC_CODE}
        language="python"
        title="custom_metrics_remote.py"
        fontSize={15}
      />
    </AbsoluteFill>
  );
};
