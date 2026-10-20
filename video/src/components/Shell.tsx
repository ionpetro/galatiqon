import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { clamp, easeInOut } from "./ui";
import { C } from "../theme";

/* Scene wrapper: masked wipe in (with a glowing green hairline riding the mask edge), soft exit. */
export const Shell: React.FC<{ children: React.ReactNode; dur: number; enter?: "wipe" | "rise" | "fade" | "none"; exit?: boolean; inLen?: number }> = ({ children, dur, enter = "wipe", exit = true, inLen = 18 }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const p = enter === "none" ? 1 : interpolate(frame, [0, inLen], [0, 1], { ...clamp, easing: easeInOut });
  const out = exit ? interpolate(frame, [dur - 12, dur], [0, 1], { ...clamp, easing: easeInOut }) : 0;
  let clip = "none";
  let line: React.ReactNode = null;
  if (enter === "wipe" && p < 1) {
    clip = `inset(0 ${(1 - p) * 100}% 0 0)`;
    line = <div style={{ position: "absolute", top: 0, bottom: 0, left: p * width - 1, width: 2, background: C.accent, boxShadow: `0 0 30px 6px rgba(34,211,154,0.55)`, opacity: Math.sin(p * Math.PI) }} />;
  } else if (enter === "rise" && p < 1) {
    clip = `inset(${(1 - p) * 100}% 0 0 0)`;
    line = <div style={{ position: "absolute", left: 0, right: 0, top: (1 - p) * height - 1, height: 2, background: C.accent, boxShadow: `0 0 30px 6px rgba(34,211,154,0.55)`, opacity: Math.sin(p * Math.PI) }} />;
  }
  const fadeIn = enter === "fade" ? p : 1;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ clipPath: clip, opacity: fadeIn * (1 - out), filter: out > 0 ? `blur(${out * 10}px)` : undefined, transform: `scale(${1 + out * 0.04})` }}>{children}</AbsoluteFill>
      {line}
    </AbsoluteFill>
  );
};
