import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { GalatiqonCanvas, projectPoint, CameraState, DeviceState, ScreenState } from "../components/Device3D";
import { Chip, Eyebrow, MaskedWords, clamp, easeInOut, easeOut } from "../components/ui";
import { C, MONO, SANS } from "../theme";

const typed = (s: string, frame: number, start: number, cps = 0.9) => s.slice(0, Math.max(0, Math.floor((frame - start) * cps)));

const PEOPLE = ["Scott", "Tom", "Barric"];

/* A glowing message packet travelling along an arc between two screen points, with a dotted trail. */
const Packet: React.FC<{ a: { x: number; y: number }; b: { x: number; y: number }; t0: number; len: number; label: string }> = ({ a, b, t0, len, label }) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [t0, t0 + len], [0, 1], { ...clamp, easing: easeInOut });
  const fade = interpolate(frame, [t0 - 4, t0, t0 + len, t0 + len + 14], [0, 1, 1, 0], clamp);
  if (fade <= 0) return null;
  const lift = 170;
  const pt = (u: number) => {
    const mx = (a.x + b.x) / 2,
      my = Math.min(a.y, b.y) - lift;
    const x = (1 - u) * (1 - u) * a.x + 2 * (1 - u) * u * mx + u * u * b.x;
    const y = (1 - u) * (1 - u) * a.y + 2 * (1 - u) * u * my + u * u * b.y;
    return { x, y };
  };
  const dots = [];
  for (let i = 0; i <= 60; i++) {
    const u = i / 60;
    const p = pt(u);
    const on = u <= t;
    dots.push(<circle key={i} cx={p.x} cy={p.y} r={on ? 3 : 1.6} fill={on ? C.accent : "rgba(255,255,255,0.25)"} opacity={on ? 0.35 + 0.65 * (1 - (t - u) * 3) : 1} />);
  }
  const head = pt(t);
  return (
    <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, opacity: fade, overflow: "visible" }}>
      {dots}
      <circle cx={head.x} cy={head.y} r={34} fill="rgba(34,211,154,0.18)" />
      <circle cx={head.x} cy={head.y} r={11} fill={C.accent} />
      <foreignObject x={head.x - 160} y={head.y - 78} width={320} height={50}>
        <div style={{ display: "flex", justifyContent: "center" }}>
          <div style={{ fontFamily: MONO, fontSize: 17, color: C.black, background: C.white, borderRadius: 999, padding: "7px 16px", whiteSpace: "nowrap" }}>{label}</div>
        </div>
      </foreignObject>
    </svg>
  );
};

export const S6Bots: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const ASK = 40,
    SEND = 92,
    TOM = 132,
    BACK = 160,
    SAY = 200;
  const down = spring({ frame: frame - ASK, fps, config: { damping: 12, stiffness: 300 } });
  const up = spring({ frame: frame - SEND, fps, config: { damping: 12, stiffness: 300 } });
  const press = Math.max(0, down - up);

  let scott: ScreenState = { text: "Hold to talk", mode: "idle" };
  if (frame >= ASK && frame < SEND) scott = { text: "Listening…", mode: "listening", eq: 0.9 };
  else if (frame >= SEND && frame < SAY) scott = { text: "Messaging Tom…", mode: "idle", eq: 0.15 };
  else if (frame >= SAY) scott = { text: typed("Tom is free at 3.", frame, SAY, 0.8), eq: frame < SAY + 50 ? 1 : 0.25 };
  let tom: ScreenState = { text: "Deck review at 4.", mode: "idle" };
  if (frame >= SEND + 34 && frame < BACK + 10) tom = { text: "Scott: free at 3?", eq: 0.8 };
  else if (frame >= BACK + 10) tom = { text: "Sent: free at 3.", mode: "idle", eq: 0 };
  const barric: ScreenState = { text: "Pipeline review at 10.", mode: "idle" };

  const xs = [-2.1, 0, 2.1];
  const devs: DeviceState[] = xs.map((x, i) => {
    const e = spring({ frame: frame - i * 6, fps, config: { damping: 16, stiffness: 70 } });
    return {
      position: [x, -0.42 + (1 - e) * -2 + Math.sin(frame / 24 + i) * 0.015, 0],
      rotY: -x * 0.14,
      rotX: 0.05,
      scale: 0.95,
      press: i === 0 ? press : 0,
      glow: i === 1 ? interpolate(frame, [TOM - 6, TOM, BACK, BACK + 10], [0, 1, 1, 0], clamp) : 0,
      screen: [scott, tom, barric][i],
    };
  });
  const cam: CameraState = { pos: [0, 0.75, interpolate(frame, [0, dur], [7.4, 6.9])], target: [0, -0.05, 0], fov: 30 };
  const tops = devs.map((d) => projectPoint([0, 0.0526, 0.025], d, cam, width, height, "button"));
  const bottoms = devs.map((d) => projectPoint([0, -0.055, 0.03], d, cam, width, height));

  const bubble = interpolate(frame, [ASK + 4, ASK + 14], [0, 1], { ...clamp, easing: easeOut });
  const spoken = interpolate(frame, [SAY, SAY + 12], [0, 1], { ...clamp, easing: easeOut });
  return (
    <AbsoluteFill style={{ fontFamily: SANS }}>
      <div style={{ position: "absolute", left: 0, right: 0, top: 110, display: "flex", flexDirection: "column", alignItems: "center" }}>
        <Eyebrow delay={0}>Bot to bot</Eyebrow>
        <div style={{ fontSize: 84, fontWeight: 500, color: C.white, letterSpacing: "-0.03em", marginTop: 24 }}>
          <MaskedWords text="Every Galatiqon can ask the others." delay={6} stagger={3} highlight={["others"]} />
        </div>
      </div>
      <GalatiqonCanvas width={width} height={height} devices={devs} cam={cam} />
      {/* name plates */}
      {PEOPLE.map((p, i) => {
        const s = interpolate(frame, [14 + i * 6, 30 + i * 6], [0, 1], { ...clamp, easing: easeOut });
        return (
          <div key={p} style={{ position: "absolute", left: bottoms[i].x - 150, width: 300, top: bottoms[i].y + 60, textAlign: "center", opacity: s, transform: `translateY(${(1 - s) * 16}px)` }}>
            <div style={{ fontFamily: MONO, fontSize: 16, letterSpacing: "0.32em", color: C.accent }}>GROK BOT</div>
            <div style={{ fontSize: 40, fontWeight: 500, color: C.white, marginTop: 6 }}>{p}</div>
          </div>
        );
      })}
      {/* Scott's question */}
      <div style={{ position: "absolute", left: tops[0].x - 230, top: tops[0].y - 130, opacity: bubble * interpolate(frame, [SEND, SEND + 8], [1, 0], clamp), transform: `translateY(${(1 - bubble) * 14}px)` }}>
        <div style={{ padding: "16px 26px", borderRadius: 22, border: `1px solid ${C.hair}`, background: "rgba(255,255,255,0.05)", fontSize: 32, color: C.white, whiteSpace: "nowrap" }}>“{typed("Ask Tom if he's free at three.", frame, ASK + 4, 0.7)}{typed("Ask Tom if he's free at three.", frame, ASK + 4, 0.7).length === 30 ? "”" : ""}</div>
      </div>
      <div style={{ position: "absolute", left: tops[0].x - 200, top: tops[0].y - 130, opacity: spoken, transform: `translateY(${(1 - spoken) * 14}px)` }}>
        <div style={{ padding: "16px 26px", borderRadius: 22, background: C.white, color: C.black, fontSize: 34, fontWeight: 500, whiteSpace: "nowrap" }}>“Tom is free at 3.”</div>
      </div>
      {frame >= TOM - 4 && frame < BACK + 20 && (
        <div style={{ position: "absolute", left: tops[1].x - 100, top: tops[1].y - 110 }}>
          <Chip delay={TOM - 4} active={0.6}>
            checks Calendar
          </Chip>
        </div>
      )}
      <Packet a={tops[0]} b={tops[1]} t0={SEND} len={38} label="scott → tom" />
      <Packet a={tops[1]} b={tops[0]} t0={BACK} len={36} label="tom → scott" />
    </AbsoluteFill>
  );
};
