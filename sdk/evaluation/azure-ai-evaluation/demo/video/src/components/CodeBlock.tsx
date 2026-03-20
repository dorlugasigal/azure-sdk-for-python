import React from "react";
import { useCurrentFrame, interpolate, spring } from "remotion";
import { COLORS, FONTS, FPS } from "../styles";

interface Annotation {
  lineRange: [number, number];
  label: string;
  color: string;
  startFrame?: number;
  endFrame?: number;
}

interface CodeBlockProps {
  code: string;
  language: "yaml" | "python";
  title?: string;
  annotations?: Annotation[];
  fontSize?: number;
}

// Simple syntax coloring
const colorizeYaml = (line: string): React.ReactNode => {
  // Comments
  if (line.trimStart().startsWith("#")) {
    return <span style={{ color: COLORS.textMuted }}>{line}</span>;
  }
  // Key-value pairs
  const match = line.match(/^(\s*)([\w-]+)(\s*:\s*)(.*)/);
  if (match) {
    const [, indent, key, colon, value] = match;
    let valueColor = COLORS.accentGreen;
    if (value.startsWith('"') || value.startsWith("'")) valueColor = COLORS.accentGreen;
    else if (value.startsWith("[")) valueColor = COLORS.accentOrange;
    else if (value === "true" || value === "false") valueColor = COLORS.accentOrange;
    return (
      <>
        {indent}
        <span style={{ color: COLORS.accentPurple }}>{key}</span>
        <span style={{ color: COLORS.text }}>{colon}</span>
        <span style={{ color: valueColor }}>{value}</span>
      </>
    );
  }
  // List items
  if (line.trimStart().startsWith("- ")) {
    const indent = line.match(/^(\s*)/)?.[1] || "";
    const rest = line.slice(indent.length + 2);
    return (
      <>
        {indent}
        <span style={{ color: COLORS.accentOrange }}>- </span>
        <span style={{ color: COLORS.text }}>{rest}</span>
      </>
    );
  }
  return <span style={{ color: COLORS.text }}>{line}</span>;
};

const colorizePython = (line: string): React.ReactNode => {
  const keywords = ["from", "import", "class", "def", "return", "if", "elif", "else", "self"];
  const decorators = line.trimStart().startsWith("@");
  const isComment = line.trimStart().startsWith("#");
  const isDocstring = line.trimStart().startsWith('"""') || line.trimStart().startsWith("'''");

  if (isComment) return <span style={{ color: COLORS.textMuted }}>{line}</span>;
  if (isDocstring) return <span style={{ color: COLORS.accentGreen }}>{line}</span>;
  if (decorators) return <span style={{ color: COLORS.accentOrange }}>{line}</span>;

  // Highlight keywords
  const result = line;
  const parts: React.ReactNode[] = [];
  const regex = new RegExp(`\\b(${keywords.join("|")})\\b`, "g");
  let lastIndex = 0;
  let match;
  while ((match = regex.exec(result)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={lastIndex} style={{ color: COLORS.text }}>{result.slice(lastIndex, match.index)}</span>);
    }
    parts.push(<span key={match.index} style={{ color: COLORS.accentPurple }}>{match[0]}</span>);
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < result.length) {
    parts.push(<span key={lastIndex} style={{ color: COLORS.text }}>{result.slice(lastIndex)}</span>);
  }
  return parts.length > 0 ? <>{parts}</> : <span style={{ color: COLORS.text }}>{line}</span>;
};

export const CodeBlock: React.FC<CodeBlockProps> = ({
  code,
  language,
  title,
  annotations = [],
  fontSize = 15,
}) => {
  const frame = useCurrentFrame();
  const lines = code.split("\n");
  const colorize = language === "yaml" ? colorizeYaml : colorizePython;

  const opacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });

  // Find active annotation based on frame range
  const activeAnnotation = annotations.find(
    (a) => a.startFrame !== undefined && a.endFrame !== undefined
      ? frame >= a.startFrame && frame < a.endFrame
      : false
  ) || (annotations.length > 0 && !annotations[0].startFrame
    ? annotations[Math.floor(frame / 80) % (annotations.length + 1) - 1]
    : undefined
  );

  return (
    <div style={{ width: "85%", margin: "0 auto", opacity, borderRadius: 12, overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>
      {title && (
        <div style={{ backgroundColor: COLORS.bgLight, padding: "10px 20px", display: "flex", alignItems: "center", gap: 8, borderBottom: `1px solid ${COLORS.border}` }}>
          <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: COLORS.accentRed }} />
          <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: COLORS.accentOrange }} />
          <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: COLORS.accentGreen }} />
          <span style={{ marginLeft: 12, color: COLORS.textMuted, fontSize: 13, fontFamily: FONTS.mono }}>{title}</span>
        </div>
      )}
      <div style={{ backgroundColor: COLORS.bgCode, padding: "16px 20px", fontFamily: FONTS.mono, fontSize, lineHeight: 1.65, position: "relative" }}>
        {lines.map((line, i) => {
          const isHighlighted = activeAnnotation && i >= activeAnnotation.lineRange[0] && i <= activeAnnotation.lineRange[1];
          return (
            <div key={i} style={{ whiteSpace: "pre", padding: "1px 8px", borderRadius: 4, backgroundColor: isHighlighted ? `${activeAnnotation.color}15` : "transparent", borderLeft: isHighlighted ? `3px solid ${activeAnnotation.color}` : "3px solid transparent" }}>
              <span style={{ color: COLORS.textMuted, marginRight: 16, fontSize: 12, display: "inline-block", width: 24, textAlign: "right" }}>{i + 1}</span>
              {colorize(line)}
            </div>
          );
        })}
        {activeAnnotation && (
          <div style={{ position: "absolute", right: 24, top: activeAnnotation.lineRange[0] * (fontSize * 1.65 + 2) + 16, backgroundColor: activeAnnotation.color, color: "#fff", padding: "6px 14px", borderRadius: 6, fontSize: 14, fontFamily: FONTS.sans, fontWeight: 600, opacity: spring({ frame, fps: FPS, from: 0, to: 1, config: { damping: 15 } }) }}>
            {activeAnnotation.label}
          </div>
        )}
      </div>
    </div>
  );
};
