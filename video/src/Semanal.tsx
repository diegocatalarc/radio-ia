import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { Frame } from "./scenes/Frame";
import { Titular } from "./scenes/Titular";
import { Cifra } from "./scenes/Cifra";
import { Porcentaje } from "./scenes/Porcentaje";
import { Linea } from "./scenes/Linea";
import { Grafico } from "./scenes/Grafico";
import { Cierre } from "./scenes/Cierre";
import type { SceneProps, WeeklyProps } from "./types";

const Body: React.FC<{ s: SceneProps; index: number }> = ({ s, index }) => {
  switch (s.kind) {
    case "cifra":
      return <Cifra value={s.value ?? ""} text={s.onScreen} index={index} />;
    case "porcentaje":
      return <Porcentaje value={s.value ?? "0"} text={s.onScreen} index={index} />;
    case "linea":
      return <Linea text={s.onScreen} items={s.timeline ?? []} index={index} />;
    case "grafico":
      return <Grafico text={s.onScreen} chart={s.chart ?? []} index={index} />;
    case "cierre":
      return <Cierre text={s.onScreen} />;
    case "tarjeta":
      return <Titular text={s.onScreen} index={index} quote />;
    default:
      return <Titular text={s.onScreen} index={index} />;
  }
};

export const totalFrames = (props: WeeklyProps) =>
  props.scenes.reduce((n, s) => n + s.durationFrames, 0);

export const Semanal: React.FC<WeeklyProps> = ({ scenes, weekLabel }) => {
  let from = 0;
  return (
    <AbsoluteFill>
      {scenes.map((s, i) => {
        const start = from;
        from += s.durationFrames;
        return (
          <Sequence key={s.id} from={start} durationInFrames={s.durationFrames}>
            <Frame weekLabel={weekLabel} source={s.source} durationFrames={s.durationFrames} index={i}>
              <Body s={s} index={i} />
            </Frame>
            <Audio src={staticFile(s.audio)} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
