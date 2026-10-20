import React, { useLayoutEffect, useRef } from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

/* galatiq.ai's particle wave: sheets of dots riding layered sine waves, fading at the edges.
   Deterministic: time comes from the frame number. */
export const Wave: React.FC<{
  intensity?: number; // 0..1 overall alpha
  rise?: number; // 0..1, 0 = sunk below frame
  center?: number; // vertical centre as fraction of height
  amp?: number; // amplitude multiplier
  speed?: number;
  sheets?: number;
  style?: React.CSSProperties;
}> = ({ intensity = 1, rise = 1, center = 0.55, amp = 1, speed = 1, sheets = 12, style }) => {
  const ref = useRef<HTMLCanvasElement>(null);
  const frame = useCurrentFrame();
  const { width: w, height: h, fps } = useVideoConfig();
  useLayoutEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, w, h);
    if (intensity <= 0.001) return;
    const t = (frame / fps) * speed;
    const COLS = 320;
    const off = (1 - rise) * h * 0.7;
    for (let s = 0; s < sheets; s++) {
      const depth = s / (sheets - 1);
      const baseY = h * (center - 0.12 + depth * 0.3) + off;
      for (let i = 0; i <= COLS; i++) {
        const u = i / COLS;
        const x = u * w;
        const y =
          baseY +
          (Math.sin(u * 6.2 + t * 0.55 + depth * 1.7) * h * 0.11 * (1 - depth * 0.4) +
            Math.sin(u * 13.1 - t * 0.9 + s) * h * 0.035 +
            Math.cos(u * 2.3 + t * 0.3) * h * 0.06) *
            amp;
        const edge = Math.sin(u * Math.PI);
        const a = intensity * (1.0 - depth * 0.7) * (0.25 + 0.75 * edge * edge) * (0.6 + 0.4 * Math.sin(u * 9 + t * 1.3 + s));
        if (a <= 0.01) continue;
        ctx.fillStyle = `rgba(${60 + depth * 10}, ${235 - depth * 90}, ${170 - depth * 50}, ${a})`;
        const r = 3.0 - depth * 1.5;
        ctx.fillRect(x, y, r, r);
      }
    }
  }, [frame, w, h, fps, intensity, rise, center, amp, speed, sheets]);
  return <canvas ref={ref} width={w} height={h} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", ...style }} />;
};
