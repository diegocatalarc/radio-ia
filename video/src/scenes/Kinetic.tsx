import React from "react";
import { useEnter, useUnit } from "./useUnit";

const Word: React.FC<{ w: string; delay: number }> = ({ w, delay }) => {
  const u = useUnit();
  const e = useEnter(delay);
  return (
    <span style={{ display: "inline-block", opacity: e, transform: `translateY(${(1 - e) * 3 * u}px)`, marginRight: "0.28em" }}>{w}</span>
  );
};

/** Texto que entra palabra a palabra (``start`` = frame de la primera palabra). */
export const Kinetic: React.FC<{ text: string; start?: number; step?: number }> = ({ text, start = 8, step = 3 }) => (
  <>
    {text.split(/\s+/).filter(Boolean).map((w, i) => (
      <Word key={i} w={w} delay={start + i * step} />
    ))}
  </>
);
