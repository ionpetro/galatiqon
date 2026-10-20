import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Eyebrow, MaskedWords, clamp, easeOut } from "../components/ui";
import { C, MONO, SANS } from "../theme";

const STATS = [
  { k: "Temperature", v: 45.1, d: 1, u: "°C", note: "Cool" },
  { k: "CPU", v: 2, d: 0, u: "%", note: "load 0.2" },
  { k: "Memory", v: 68, d: 0, u: "%", note: "641 MB / 949 MB" },
  { k: "First spoken answer", v: 3.0, d: 1, u: "s", note: "replies stream in" },
];

const Spark: React.FC<{ seed: number; p: number }> = ({ seed, p }) => {
  const pts: string[] = [];
  for (let i = 0; i <= 40; i++) {
    const y = 30 - 12 * Math.abs(Math.sin(i * 0.7 + seed) * Math.sin(i * 0.23 + seed * 2)) - (i % 13 === 5 ? 14 : 0);
    pts.push(`${i * 9},${y}`);
  }
  return (
    <svg width={360} height={40} style={{ marginTop: 14 }}>
      <polyline points={pts.join(" ")} fill="none" stroke={C.accent} strokeWidth={2} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - p} />
    </svg>
  );
};

export const S7Dashboard: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const tilt = spring({ frame: frame - 4, fps, config: { damping: 30, stiffness: 50 } });
  const zoom = interpolate(frame, [0, dur], [1, 1.06]);
  return (
    <AbsoluteFill style={{ fontFamily: SANS }}>
      <div style={{ position: "absolute", left: 760, top: 150, width: 1240, height: 661, perspective: 1800 }}>
        <div
          style={{
            width: "100%",
            height: "100%",
            transform: `rotateY(${interpolate(tilt, [0, 1], [-34, -12])}deg) rotateX(${interpolate(tilt, [0, 1], [18, 4])}deg) translateX(${(1 - tilt) * 300}px) scale(${zoom})`,
            transformOrigin: "left center",
            borderRadius: 18,
            overflow: "hidden",
            border: `1px solid ${C.hair}`,
            boxShadow: "0 60px 160px rgba(0,154,108,0.18)",
            opacity: tilt,
          }}
        >
          <Img src={staticFile("dashboard.jpg")} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg, rgba(0,0,0,0) 50%, rgba(0,0,0,0.85))" }} />
        </div>
      </div>
      <div style={{ position: "absolute", left: 120, top: 140 }}>
        <Eyebrow delay={0}>Live from the Pi</Eyebrow>
        <div style={{ fontSize: 92, fontWeight: 500, color: C.white, letterSpacing: "-0.035em", lineHeight: 1.02, marginTop: 28 }}>
          <MaskedWords text="Watch it think." delay={6} />
        </div>
        <div style={{ fontSize: 28, fontWeight: 300, color: C.grey, marginTop: 18, opacity: interpolate(frame, [20, 36], [0, 1], clamp) }}>A dashboard served from the device itself.</div>
      </div>
      <div style={{ position: "absolute", left: 120, top: 470, display: "grid", gridTemplateColumns: "300px 300px", gap: 20 }}>
        {STATS.map((s, i) => {
          const sp = spring({ frame: frame - 20 - i * 7, fps, config: { damping: 18, stiffness: 120 } });
          const count = interpolate(frame, [24 + i * 7, 74 + i * 7], [0, s.v], { ...clamp, easing: easeOut });
          return (
            <div
              key={s.k}
              style={{
                background: "rgba(10,10,10,0.92)",
                border: `1px solid ${C.hair}`,
                borderRadius: 18,
                padding: "22px 26px",
                opacity: sp,
                transform: `translateY(${(1 - sp) * 40 + Math.sin((frame + i * 20) / 30) * 4}px)`,
                overflow: "hidden",
              }}
            >
              <div style={{ fontFamily: MONO, fontSize: 14, letterSpacing: "0.28em", color: C.accent, textTransform: "uppercase" }}>{s.k}</div>
              <div style={{ fontSize: 68, fontWeight: 400, color: C.white, marginTop: 10, fontVariantNumeric: "tabular-nums" }}>
                {count.toFixed(s.d)}
                <span style={{ fontSize: 26, color: C.grey, marginLeft: 6 }}>{s.u}</span>
              </div>
              <div style={{ fontSize: 18, color: "rgba(255,255,255,0.5)" }}>{s.note}</div>
              <Spark seed={i * 1.7} p={interpolate(frame, [30 + i * 7, 90 + i * 7], [0, 1], clamp)} />
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
