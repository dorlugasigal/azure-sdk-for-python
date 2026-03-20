import React from "react";
import { AbsoluteFill, Audio, Sequence, Series, staticFile, useCurrentFrame } from "remotion";
import { SCENE_DURATIONS, COLORS } from "./styles";
import { Subtitle } from "./components/Subtitle";
import { VOICEOVER_SEGMENTS } from "./data/voiceover";

import { TitleScene } from "./scenes/TitleScene";
import { YamlConfigScene } from "./scenes/YamlConfigScene";
import { LocalAndViewScene } from "./scenes/LocalAndViewScene";
import { RemoteAndDashboardScene } from "./scenes/RemoteAndDashboardScene";
import { OutroScene } from "./scenes/OutroScene";

export const Video: React.FC = () => {
  const frame = useCurrentFrame();

  const currentSegment = VOICEOVER_SEGMENTS.find(
    (seg) => frame >= seg.startFrame && frame < seg.endFrame
  );

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      <Series>
        <Series.Sequence durationInFrames={SCENE_DURATIONS.title}>
          <TitleScene />
          <Audio src={staticFile("audio/01-title.mp3")} volume={1} />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENE_DURATIONS.yamlConfig}>
          <YamlConfigScene />
          <Audio src={staticFile("audio/02-config.mp3")} volume={1} />
          {/* Metric narration starts after config narration (609 frames + small gap) */}
          <Sequence from={630}>
            <Audio src={staticFile("audio/03-metric.mp3")} volume={1} />
          </Sequence>
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENE_DURATIONS.localAndView}>
          <LocalAndViewScene />
          <Audio src={staticFile("audio/04-local.mp3")} volume={1} />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENE_DURATIONS.remoteAndDashboard}>
          <RemoteAndDashboardScene />
          <Audio src={staticFile("audio/06-remote.mp3")} volume={1} />
        </Series.Sequence>
        <Series.Sequence durationInFrames={SCENE_DURATIONS.outro}>
          <OutroScene />
        </Series.Sequence>
      </Series>

      {currentSegment && <Subtitle text={currentSegment.text} />}
    </AbsoluteFill>
  );
};
