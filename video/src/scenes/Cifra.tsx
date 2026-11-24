import React from "react";
import { accent, brand } from "../brand";
import { interpolate, useCurrentFrame } from "remotion";
import { useEnter, useUnit } from "./useUnit";

export const Cifra: React.FC<{ value: string; text: string; index: number }> = ({ value, text, index }) => {
  const u = useUnit();
  const pop = useEnter(9);
  const frame = useCurrentFrame();
  const isInt = /^\d{1,4}$/.test(value);
  const shown = isInt
    ? String(Math.round(interpolate(frame, [10, 34], [0, Number(value)], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })))
    : value;
  return (
    <div>
      <div style={{ fontSize: 22 * u * Math.min(1, 3.0 / Math.max(1, value.length)), lineHeight: 0.9, fontWeight: 800, letterSpacing: "-0.04em",
                    color: accent(index), transform: `scale(${0.9 + 0.1 * pop})`, transformOrigin: "left" }}>{shown}</div>
      <div style={{ marginTop: 2.4 * u, fontSize: 3.4 * u, fontWeight: 500, color: brand.fg, maxWidth: "80%" }}>{text}</div>
    </div>
  );
};
