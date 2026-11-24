import React from "react";
import { accent, brand } from "../brand";
import { useEnter, useUnit } from "./useUnit";

export const Porcentaje: React.FC<{ value: string; text: string; index: number }> = ({ value, text, index }) => {
  const u = useUnit();
  const grow = useEnter(6);
  const pct = Math.max(0, Math.min(100, parseFloat(value.replace(",", ".")))) || 0;
  const size = 28 * u;
  const stroke = 4.6 * u;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5 * u, flexWrap: "wrap" }}>
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={brand.track} strokeWidth={stroke} />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={accent(index)} strokeWidth={stroke}
                  strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={circ * (1 - (pct / 100) * grow)} />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center",
                      fontSize: 7.5 * u, fontWeight: 800 }}>{Math.round(pct * grow)}%</div>
      </div>
      <div style={{ fontSize: 4 * u, fontWeight: 700, maxWidth: 28 * u * 1.6, lineHeight: 1.2 }}>{text}</div>
    </div>
  );
};
