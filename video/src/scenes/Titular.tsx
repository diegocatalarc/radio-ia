import React from "react";
import { accent } from "../brand";
import { Kinetic } from "./Kinetic";
import { useUnit } from "./useUnit";

export const Titular: React.FC<{ text: string; index: number; quote?: boolean }> = ({ text, index, quote }) => {
  const u = useUnit();
  return (
    <div>
      <div style={{ width: 9 * u, height: 1.4 * u, borderRadius: u, background: accent(index), marginBottom: 3 * u }} />
      <div style={{ fontSize: (quote ? 4.6 : 5.4) * u, lineHeight: 1.12, fontWeight: quote ? 700 : 800,
                    letterSpacing: "-0.02em", textWrap: "balance" }}><Kinetic text={text} /></div>
    </div>
  );
};
