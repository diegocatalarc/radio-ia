import { loadFont } from "@remotion/google-fonts/Inter";

const { fontFamily } = loadFont("normal", { weights: ["500", "700", "800"], subsets: ["latin", "latin-ext"] });

export const brand = {
  bg: "#0e1230",
  panel: "#161b45",
  track: "#252b63",
  fg: "#f4f1ea",
  muted: "#9aa0c4",
  accents: ["#FFC845", "#FF5A4E", "#4D7CFF", "#2ED3B7"],
  font: fontFamily,
};

export const accent = (i: number) => brand.accents[i % brand.accents.length];
