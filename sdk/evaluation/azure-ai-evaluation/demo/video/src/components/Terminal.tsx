import React from "react";
import { useCurrentFrame, interpolate } from "remotion";
import { COLORS, FONTS } from "../styles";

interface TerminalLine {
  text: string;
  color?: string;
  isCommand?: boolean;
}

interface TerminalProps {
  lines: TerminalLine[];
  typingSpeed?: number; // frames per line
  title?: string;
}

export const Terminal: React.FC<TerminalProps> = ({
  lines,
  typingSpeed = 8,
  title = "Terminal",
}) => {
  const frame = useCurrentFrame();
  const visibleLineCount = Math.min(
    lines.length,
    Math.floor(frame / typingSpeed) + 1
  );

  return (
    <div
      style={{
        width: "85%",
        margin: "0 auto",
        borderRadius: 12,
        overflow: "hidden",
        boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
        fontFamily: FONTS.mono,
      }}
    >
      {/* Title bar */}
      <div
        style={{
          backgroundColor: COLORS.bgLight,
          padding: "12px 20px",
          display: "flex",
          alignItems: "center",
          gap: 8,
          borderBottom: `1px solid ${COLORS.border}`,
        }}
      >
        <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: COLORS.accentRed }} />
        <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: COLORS.accentOrange }} />
        <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: COLORS.accentGreen }} />
        <span style={{ marginLeft: 12, color: COLORS.textMuted, fontSize: 14 }}>{title}</span>
      </div>
      {/* Terminal body */}
      <div
        style={{
          backgroundColor: COLORS.terminal,
          padding: "20px 24px",
          minHeight: 400,
          fontSize: 16,
          lineHeight: 1.7,
        }}
      >
        {lines.slice(0, visibleLineCount).map((line, i) => {
          const lineFrame = i * typingSpeed;
          const charProgress = interpolate(
            frame - lineFrame,
            [0, Math.max(typingSpeed - 2, 1)],
            [0, line.text.length],
            { extrapolateRight: "clamp" }
          );
          const visibleText = line.text.slice(0, Math.floor(charProgress));
          const showCursor = i === visibleLineCount - 1 && charProgress < line.text.length;

          return (
            <div key={i} style={{ color: line.color || COLORS.terminalWhite, whiteSpace: "pre" }}>
              {line.isCommand && <span style={{ color: COLORS.terminalGreen }}>❯ </span>}
              {visibleText}
              {showCursor && (
                <span
                  style={{
                    backgroundColor: COLORS.text,
                    width: 8,
                    height: 18,
                    display: "inline-block",
                    opacity: Math.sin(frame * 0.3) > 0 ? 1 : 0,
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
