import React from "react";
import { Composition } from "remotion";
import { Semanal, totalFrames } from "./Semanal";
import type { WeeklyProps } from "./types";

const defaults: WeeklyProps = { fps: 30, title: "Radio IA", weekLabel: "", scenes: [] };

const meta = async ({ props }: { props: WeeklyProps }) => ({
  durationInFrames: Math.max(1, totalFrames(props)),
  fps: props.fps,
});

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Semanal16x9" component={Semanal} width={1920} height={1080} fps={30}
                 durationInFrames={30} defaultProps={defaults} calculateMetadata={meta} />
    <Composition id="Semanal9x16" component={Semanal} width={1080} height={1920} fps={30}
                 durationInFrames={30} defaultProps={defaults} calculateMetadata={meta} />
  </>
);
