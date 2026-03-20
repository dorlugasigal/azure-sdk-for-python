import React from "react";
import { useCurrentFrame, interpolate, spring } from "remotion";
import { COLORS, FONTS, FPS } from "../styles";

interface BrowserProps {
  url: string;
  children: React.ReactNode;
}

export const Browser: React.FC<BrowserProps> = ({ url, children }) => {
  const frame = useCurrentFrame();
  const scale = spring({ frame, fps: FPS, from: 0.95, to: 1, config: { damping: 15 } });
  const opacity = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });

  return (
    <div style={{ width: "88%", margin: "0 auto", borderRadius: 12, overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.5)", transform: `scale(${scale})`, opacity }}>
      {/* Browser chrome */}
      <div style={{ backgroundColor: COLORS.bgLight, padding: "10px 16px", display: "flex", alignItems: "center", gap: 10, borderBottom: `1px solid ${COLORS.border}` }}>
        <div style={{ display: "flex", gap: 6 }}>
          <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: COLORS.accentRed }} />
          <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: COLORS.accentOrange }} />
          <div style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: COLORS.accentGreen }} />
        </div>
        <div style={{ flex: 1, backgroundColor: COLORS.bg, borderRadius: 6, padding: "6px 14px", fontSize: 13, color: COLORS.textMuted, fontFamily: FONTS.mono }}>
          {url}
        </div>
      </div>
      {/* Browser content */}
      <div style={{ backgroundColor: "#fff", minHeight: 500, padding: 0 }}>
        {children}
      </div>
    </div>
  );
};
