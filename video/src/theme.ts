import { loadFont as loadAlbert } from "@remotion/google-fonts/AlbertSans";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

export const { fontFamily: SANS } = loadAlbert("normal", { weights: ["300", "400", "500", "600", "700"], subsets: ["latin"] });
export const { fontFamily: MONO } = loadMono("normal", { weights: ["400", "500"], subsets: ["latin"] });

export const C = {
  black: "#000000",
  ink: "#070707",
  white: "#ffffff",
  green: "#009a6c",
  accent: "#22d39a",
  board: "#202020",
  grey: "#cfcfcf",
  dim: "rgba(255,255,255,0.55)",
  hair: "rgba(255,255,255,0.1)",
  product: "#13b37f",
};

export const FPS = 30;
