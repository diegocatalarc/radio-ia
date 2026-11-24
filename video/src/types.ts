// Forma de props.json: la produce radio/video/manifest.py (Task 6).
export type Kind = "titular" | "cifra" | "grafico" | "tarjeta" | "porcentaje" | "linea" | "cierre";

export type SceneProps = {
  id: string;
  kind: Kind;
  onScreen: string;
  value: string | null;
  chart: { label: string; value: number }[] | null;
  timeline: { when: string; label: string }[] | null;
  source: string | null;
  audio: string;
  durationFrames: number;
};

export type WeeklyProps = {
  fps: number;
  title: string;
  weekLabel: string;
  scenes: SceneProps[];
};
