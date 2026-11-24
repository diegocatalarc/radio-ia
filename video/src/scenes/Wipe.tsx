import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { accent } from "../brand";

/** Barrido de color que cruza la pantalla al empezar cada escena (frames 0 a 16). */
export const Wipe: React.FC<{ index: number }> = ({ index }) => {
  const frame = useCurrentFrame();
  if (frame > 16) return null;
  const x = interpolate(frame, [0, 8, 16], [-100, 0, 100], {
    easing: Easing.inOut(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return <AbsoluteFill style={{ background: accent(index), transform: `translateX(${x}%)`, zIndex: 10 }} />;
};
