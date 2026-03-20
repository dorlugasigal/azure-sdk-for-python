import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate, spring } from "remotion";
import { COLORS, FONTS, FPS } from "../styles";
import { CodeBlock } from "../components/CodeBlock";
import { YAML_CONFIG, YAML_ANNOTATIONS, CUSTOM_METRIC_CODE } from "../data/yamlContent";

const VARIANTS = [
  { model: "gpt-4.1-mini", temp: "0.3" },
  { model: "gpt-4.1-mini", temp: "0.9" },
  { model: "gpt-4.1", temp: "0.3" },
  { model: "gpt-4.1", temp: "0.9" },
];

export const YamlConfigScene: React.FC = () => {
  const frame = useCurrentFrame();
  const headerOpacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });

  // Phase 1: Variants panel (frames 40-560)
  const variantsOpacity = frame >= 40 && frame < 560
    ? interpolate(frame, [40, 60, 530, 560], [0, 1, 1, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" })
    : 0;

  // Phase 2: Custom metric code slides in and grows (frames 620-890)
  const metricPhase = frame >= 620;
  const metricOpacity = metricPhase
    ? interpolate(frame, [620, 660, 870, 895], [0, 1, 1, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" })
    : 0;
  // Slide in from right
  const metricSlideX = metricPhase
    ? interpolate(frame, [620, 680], [400, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" })
    : 400;
  // Fade out the yaml when metric takes over
  const yamlOpacity = metricPhase
    ? interpolate(frame, [620, 670], [1, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" })
    : 1;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "40px 60px",
        gap: 20,
      }}
    >
      {/* YAML config + sidebar — fades out when metric takes over */}
      <div style={{ opacity: yamlOpacity }}>
        <div
          style={{
            fontSize: 28,
            fontFamily: FONTS.sans,
            fontWeight: 600,
            color: COLORS.text,
            opacity: headerOpacity,
            marginBottom: 8,
          }}
        >
          📋 Experiment Configuration
        </div>
        <div style={{ display: "flex", gap: 24 }}>
          <div style={{ flex: 1 }}>
            <CodeBlock
              code={YAML_CONFIG}
              language="yaml"
              title="evals_model_comparison.yaml"
              annotations={YAML_ANNOTATIONS}
              fontSize={13}
            />
          </div>
          {/* Right panel — variants */}
          <div style={{ width: 520, position: "relative", paddingTop: 44 }}>
            <div
              style={{
                opacity: variantsOpacity,
                display: "flex",
                flexDirection: "column",
                gap: 16,
                position: "absolute",
                top: 44,
                left: 0,
                right: 0,
              }}
            >
              <div
                style={{
                  fontSize: 20,
                  fontFamily: FONTS.sans,
                  fontWeight: 600,
                  color: COLORS.accent,
                  marginBottom: 4,
                }}
              >
                🔄 Cartesian Product → 4 Runs
              </div>
              {VARIANTS.map((v, i) => {
                const delay = 60 + i * 20;
                const rowScale = spring({ frame: frame - delay, fps: FPS, from: 0.8, to: 1, config: { damping: 12 } });
                const rowOpacity = interpolate(frame - delay, [0, 15], [0, 1], { extrapolateRight: "clamp" });
                return (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      backgroundColor: COLORS.bgLight,
                      borderRadius: 10,
                      padding: "16px 20px",
                      border: `1px solid ${COLORS.border}`,
                      opacity: rowOpacity,
                      transform: `scale(${rowScale})`,
                    }}
                  >
                    <div style={{ fontSize: 18, fontFamily: FONTS.mono, color: COLORS.accent, fontWeight: 700, width: 32 }}>
                      #{i + 1}
                    </div>
                    <div style={{ fontSize: 18, fontFamily: FONTS.mono, color: COLORS.text, fontWeight: 500 }}>
                      {v.model}
                    </div>
                    <div
                      style={{
                        fontSize: 15,
                        fontFamily: FONTS.mono,
                        color: COLORS.accentPurple,
                        backgroundColor: `${COLORS.accentPurple}20`,
                        padding: "4px 14px",
                        borderRadius: 12,
                        marginLeft: "auto",
                        fontWeight: 600,
                      }}
                    >
                      temperature={v.temp}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Custom metric code — slides in from right, centered fullscreen */}
      {metricPhase && (
        <AbsoluteFill
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "40px 120px",
            opacity: metricOpacity,
            transform: `translateX(${metricSlideX}px)`,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              marginBottom: 20,
            }}
          >
            <div style={{ fontSize: 32, fontFamily: FONTS.sans, fontWeight: 700, color: COLORS.text }}>
              🎯 Custom Metric: Conciseness
            </div>
            <div
              style={{
                fontSize: 16,
                fontFamily: FONTS.mono,
                color: COLORS.accentOrange,
                backgroundColor: `${COLORS.accentOrange}20`,
                padding: "6px 16px",
                borderRadius: 12,
                border: `1px solid ${COLORS.accentOrange}40`,
                fontWeight: 600,
              }}
            >
              grade() function
            </div>
          </div>
          <div style={{ width: "100%", maxWidth: 900 }}>
            <CodeBlock
              code={CUSTOM_METRIC_CODE}
              language="python"
              title="custom_metrics_remote.py"
              fontSize={18}
            />
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
