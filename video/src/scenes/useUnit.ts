import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

/** Unidad de diseño: igual en 16:9 y 9:16 (lado corto / 56,25) para que los textos escalen. */
export const useUnit = () => {
  const { width, height } = useVideoConfig();
  return Math.min(width, height) / 56.25;
};

/** Entrada suave 0→1 con retraso opcional en frames. */
export const useEnter = (delay = 0) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping: 200 }, durationInFrames: 18 });
};

export const useFadeOutTail = (durationFrames: number) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [durationFrames - 6, durationFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
};
