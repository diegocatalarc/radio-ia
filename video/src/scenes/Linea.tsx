import React from "react";
import { accent, brand } from "../brand";
import { useEnter, useUnit } from "./useUnit";

export const Linea: React.FC<{ text: string; items: { when: string; label: string }[]; index: number }> = ({
  text, items, index,
}) => {
  const u = useUnit();
  const line = useEnter(4);
  return (
    <div>
      <div style={{ fontSize: 3.6 * u, fontWeight: 700, marginBottom: 4 * u, lineHeight: 1.2 }}>{text}</div>
      <div style={{ position: "relative", display: "flex", gap: 3 * u, flexWrap: "wrap" }}>
        <div style={{ position: "absolute", left: 0, top: 1.1 * u, height: 0.5 * u, background: brand.track,
                      width: `${line * 100}%` }} />
        {items.map((t, j) => (
          <TimelineItem key={t.when + j} item={t} color={accent(index + j)} delay={10 + j * 14} />
        ))}
      </div>
    </div>
  );
};

const TimelineItem: React.FC<{ item: { when: string; label: string }; color: string; delay: number }> = ({
  item, color, delay,
}) => {
  const u = useUnit();
  const e = useEnter(delay);
  return (
    <div style={{ flex: "1 1 18%", position: "relative", paddingTop: 4 * u, opacity: e,
                  transform: `translateY(${(1 - e) * 2 * u}px)` }}>
      <div style={{ position: "absolute", top: 0, left: 0, width: 2.4 * u, height: 2.4 * u, borderRadius: "50%", background: color }} />
      <div style={{ fontSize: 2.5 * u, fontWeight: 700, color: brand.muted, textTransform: "uppercase", letterSpacing: "0.08em" }}>{item.when}</div>
      <div style={{ fontSize: 3.3 * u, fontWeight: 700, lineHeight: 1.2 }}>{item.label}</div>
    </div>
  );
};
