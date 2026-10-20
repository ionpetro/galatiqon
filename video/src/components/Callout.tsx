import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { clamp, easeOut } from "./ui";
import { C, MONO, SANS } from "../theme";

/* Hairline callout: pulsing dot on the part, an elbow line that draws itself, a masked label. */
export const Callout: React.FC<{ ax: number; ay: number; lx: number; ly: number; delay: number; index: string; title: string; sub?: string; out?: number }> = ({ ax, ay, lx, ly, delay, index, title, sub, out = 0 }) => {
  const frame = useCurrentFrame();
  const f = frame - delay;
  const dot = interpolate(f, [0, 10], [0, 1], { ...clamp, easing: easeOut });
  const draw = interpolate(f, [6, 26], [0, 1], { ...clamp, easing: easeOut });
  const lab = interpolate(f, [20, 38], [0, 1], { ...clamp, easing: easeOut });
  const fade = 1 - out;
  if (f < 0) return null;
  const right = lx >= ax;
  const dy = ly - ay;
  const ex = ax + (right ? 1 : -1) * Math.min(Math.abs(dy), Math.abs(lx - ax) * 0.6);
  const d = `M ${ax} ${ay} L ${ex} ${ly} L ${lx} ${ly}`;
  const ring = (f % 45) / 45;
  return (
    <div style={{ position: "absolute", inset: 0, opacity: fade, pointerEvents: "none" }}>
      <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <path d={d} stroke="rgba(255,255,255,0.55)" strokeWidth={1.5} fill="none" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} />
        <circle cx={ax} cy={ay} r={7 * dot} fill={C.accent} />
        <circle cx={ax} cy={ay} r={7 + ring * 22} fill="none" stroke={C.accent} strokeWidth={1.5} opacity={(1 - ring) * dot * 0.8} />
        <circle cx={lx} cy={ly} r={3 * draw} fill="#fff" />
      </svg>
      <div
        style={{
          position: "absolute",
          top: ly - 46,
          left: right ? lx + 18 : undefined,
          right: right ? undefined : `calc(100% - ${lx - 18}px)`,
          textAlign: right ? "left" : "right",
          clipPath: right ? `inset(0 ${(1 - lab) * 100}% 0 0)` : `inset(0 0 0 ${(1 - lab) * 100}%)`,
          whiteSpace: "nowrap",
        }}
      >
        <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: "0.3em", color: C.accent, marginBottom: 6 }}>{index}</div>
        <div style={{ fontFamily: SANS, fontSize: 34, fontWeight: 500, color: C.white, lineHeight: 1.1 }}>{title}</div>
        {sub && <div style={{ fontFamily: SANS, fontSize: 21, fontWeight: 300, color: C.grey, marginTop: 6 }}>{sub}</div>}
      </div>
    </div>
  );
};
