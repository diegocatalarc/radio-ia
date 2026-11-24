import React from "react";
import { brand } from "../brand";
import { useUnit } from "./useUnit";

export const Cierre: React.FC<{ text: string }> = ({ text }) => {
  const u = useUnit();
  return (
    <div>
      <div style={{ letterSpacing: "0.3em", textTransform: "uppercase", fontSize: 3 * u, color: brand.muted,
                    fontWeight: 700, marginBottom: 2.4 * u }}>Radio IA</div>
      <div style={{ fontSize: 5.4 * u, fontWeight: 800, lineHeight: 1.12, letterSpacing: "-0.02em", textWrap: "balance" }}>{text}</div>
    </div>
  );
};
