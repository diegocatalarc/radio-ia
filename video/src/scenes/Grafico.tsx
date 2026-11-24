import React from "react";
import { accent, brand } from "../brand";
import { useEnter, useUnit } from "./useUnit";

export const Grafico: React.FC<{ text: string; chart: { label: string; value: number }[]; index: number }> = ({
  text, chart, index,
}) => {
  const u = useUnit();
  const top = Math.max(...chart.map((c) => c.value), 1);
  return (
    <div>
      <div style={{ fontSize: 3.6 * u, fontWeight: 700, marginBottom: 4 * u, lineHeight: 1.2 }}>{text}</div>
      {chart.map((c, j) => (
        <Bar key={c.label + j} label={c.label} value={c.value} pct={c.value / top} color={accent(index + j)} delay={8 + j * 8} />
      ))}
    </div>
  );
};

const Bar: React.FC<{ label: string; value: number; pct: number; color: string; delay: number }> = ({
  label, value, pct, color, delay,
}) => {
  const u = useUnit();
  const e = useEnter(delay);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 2 * u, marginTop: 2 * u }}>
      <div style={{ width: "26%", fontSize: 2.6 * u, color: brand.muted }}>{label}</div>
      <div style={{ height: 3.4 * u, borderRadius: 0.8 * u, background: color, width: `${pct * 52 * e}%` }} />
      <div style={{ fontSize: 3 * u, fontWeight: 700 }}>{value}</div>
    </div>
  );
};
