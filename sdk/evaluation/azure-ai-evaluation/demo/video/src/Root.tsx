import React from "react";
import { Composition } from "remotion";
import { Video } from "./Video";
import { TOTAL_FRAMES, FPS } from "./styles";

export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="EvaluationDemo"
        component={Video}
        durationInFrames={TOTAL_FRAMES}
        fps={FPS}
        width={1920}
        height={1080}
      />
    </>
  );
};
