import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { accent } from "../brand";
import { useUnit } from "./useUnit";

/** Formas geométricas planas que derivan despacio; la paleta rota con el índice de la escena. */
export const Background: React.FC<{ index: number }> = ({ index }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const u = useUnit();
  const t = frame / fps;
  const flip = index % 2 === 0 ? 1 : -1;
  return (
    <AbsoluteFill style={{ overflow: "hidden", pointerEvents: "none" }}>
      <div style={{ position: "absolute", right: -9 * u + Math.sin(t * 0.7) * 2.4 * u, top: -11 * u + Math.cos(t * 0.6) * 2.4 * u,
                    width: 36 * u, height: 36 * u, borderRadius: "50%", background: accent(index), opacity: 0.15,
                    transform: `scale(${1 + 0.04 * Math.sin(t)})` }} />
      <div style={{ position: "absolute", left: -7 * u + Math.cos(t * 0.5) * 2 * u, bottom: -9 * u + Math.sin(t * 0.8) * 2 * u,
                    width: 30 * u, height: 30 * u, borderRadius: "50%", border: `${2.2 * u}px solid ${accent(index + 1)}`,
                    opacity: 0.32 }} />
      <div style={{ position: "absolute", right: 12 * u, bottom: 12 * u + Math.sin(t * 0.9) * 1.5 * u, width: 11 * u,
                    height: 11 * u, borderRadius: 1.6 * u, background: accent(index + 2), opacity: 0.2,
                    transform: `rotate(${flip * t * 14}deg)` }} />
      <div style={{ position: "absolute", right: 6 * u, bottom: 40 * u, width: 4 * u, height: 4 * u, borderRadius: "50%",
                    background: accent(index + 3), opacity: 0.35, transform: `translateY(${Math.sin(t * 1.4) * 1.2 * u}px)` }} />
    </AbsoluteFill>
  );
};
