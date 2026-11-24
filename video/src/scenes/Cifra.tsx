import React from "react";
import { accent, brand } from "../brand";
import { useEnter, useUnit } from "./useUnit";

export const Cifra: React.FC<{ value: string; text: string; index: number }> = ({ value, text, index }) => {
  const u = useUnit();
  const pop = useEnter(4);
  return (
    <div>
      <div style={{ fontSize: 22 * u, lineHeight: 0.9, fontWeight: 800, letterSpacing: "-0.04em",
                    color: accent(index), transform: `scale(${0.9 + 0.1 * pop})`, transformOrigin: "left" }}>{value}</div>
      <div style={{ marginTop: 2.4 * u, fontSize: 3.4 * u, fontWeight: 500, color: brand.fg, maxWidth: "80%" }}>{text}</div>
    </div>
  );
};
