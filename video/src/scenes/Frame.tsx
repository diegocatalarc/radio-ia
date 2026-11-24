import React from "react";
import { AbsoluteFill } from "remotion";
import { brand } from "../brand";
import { useEnter, useFadeOutTail, useUnit } from "./useUnit";

type Props = {
  weekLabel: string;
  source: string | null;
  durationFrames: number;
  children: React.ReactNode;
};

/** Marco común: etiqueta superior, contenido centrado y rótulo de fuente inferior. */
export const Frame: React.FC<Props> = ({ weekLabel, source, durationFrames, children }) => {
  const u = useUnit();
  const enter = useEnter();
  const lower = useEnter(10);
  const fade = useFadeOutTail(durationFrames);
  return (
    <AbsoluteFill style={{ background: brand.bg, color: brand.fg, fontFamily: brand.font, opacity: fade }}>
      <div style={{ position: "absolute", left: 5 * u, right: 5 * u, top: 4 * u, fontSize: 1.9 * u, fontWeight: 700,
                    letterSpacing: "0.18em", textTransform: "uppercase", color: brand.muted }}>
        Radio IA · {weekLabel}
      </div>
      <AbsoluteFill style={{ justifyContent: "center", padding: `0 ${8 * u}px`,
                             opacity: enter, transform: `translateY(${(1 - enter) * 2 * u}px)` }}>
        {children}
      </AbsoluteFill>
      {source ? (
        <div style={{ position: "absolute", left: 0, bottom: 5 * u, background: brand.panel,
                      padding: `${1.1 * u}px ${3 * u}px ${1.1 * u}px ${5 * u}px`, fontSize: 2.2 * u,
                      fontWeight: 700, borderLeft: `${1 * u}px solid ${brand.accents[0]}`,
                      opacity: lower, transform: `translateX(${(1 - lower) * -6 * u}px)` }}>
          <span style={{ color: brand.muted, marginRight: 1.6 * u, textTransform: "uppercase",
                         fontSize: 1.8 * u, letterSpacing: "0.14em" }}>Fuente</span>
          {source}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
