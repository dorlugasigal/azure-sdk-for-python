import React from "react";
import { FONTS } from "../styles";

interface SubtitleProps {
  text: string;
}

export const Subtitle: React.FC<SubtitleProps> = ({ text }) => {
  const opacity = 1;

  return (
    <div
      style={{
        position: "absolute",
        bottom: 60,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        zIndex: 100,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0, 0, 0, 0.75)",
          color: "#fff",
          padding: "12px 28px",
          borderRadius: 8,
          fontSize: 22,
          fontFamily: FONTS.sans,
          fontWeight: 500,
          maxWidth: "75%",
          textAlign: "center",
          lineHeight: 1.4,
          opacity,
          backdropFilter: "blur(8px)",
        }}
      >
        {text}
      </div>
    </div>
  );
};
