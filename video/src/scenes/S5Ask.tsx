import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { GalatiqonCanvas, projectPoint, CameraState, DeviceState, ScreenState } from "../components/Device3D";
import { Chip, Eq, Eyebrow, MaskedWords, clamp, easeOut } from "../components/ui";
import { C, MONO, SANS } from "../theme";

const Q = "When is the Acme renewal call?";
const A1 = "Thursday at 2 with Dana.";
const A2 = "She wants the pricing deck first.";
const SOURCES = ["Company brief", "Calendar", "Gmail", "Slack", "CRM"];

const typed = (s: string, frame: number, start: number, cps = 0.9) => s.slice(0, Math.max(0, Math.floor((frame - start) * cps)));

export const S5Ask: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const PRESS = 56,
    RELEASE = 128,
    REPLY = 168;
  const down = spring({ frame: frame - PRESS, fps, config: { damping: 12, stiffness: 300 } });
  const up = spring({ frame: frame - RELEASE, fps, config: { damping: 12, stiffness: 300 } });
  const press = Math.max(0, down - up);
  let screen: ScreenState = { text: "Hold to talk", mode: "idle", eq: 0 };
  if (frame >= PRESS && frame < RELEASE) screen = { text: "Listening…", mode: "listening", eq: 0.9 };
  else if (frame >= RELEASE && frame < REPLY) screen = { text: "Asking Grok Bot…", mode: "idle", eq: 0.15 };
  else if (frame >= REPLY && frame < REPLY + 70) screen = { text: typed(A1, frame, REPLY, 0.8), eq: 1 };
  else if (frame >= REPLY + 70) screen = { text: typed(A2, frame, REPLY + 70, 0.8), eq: frame < REPLY + 130 ? 1 : 0.2 };

  const enter = spring({ frame, fps, config: { damping: 200 } });
  const dev: DeviceState = { position: [0.95, (1 - enter) * -0.4 + Math.sin(frame / 25) * 0.015, 0], rotY: -0.32 + Math.sin(frame / 60) * 0.03, rotX: 0.06, press, glow: press, screen };
  const cam: CameraState = { pos: [0.3, 0.45, interpolate(frame, [0, dur], [4.4, 3.9])], target: [0.25, 0, 0], fov: 30 };
  const btn = projectPoint([0, 0.0526, 0.025], dev, cam, width, height, "button");

  const qIn = interpolate(frame, [PRESS, PRESS + 10], [0, 1], { ...clamp, easing: easeOut });
  const srcIn = (i: number) => interpolate(frame, [RELEASE + 4 + i * 6, RELEASE + 14 + i * 6], [0, 1], clamp);
  const timer = interpolate(frame, [RELEASE, REPLY], [0, 2.9], clamp);
  const aIn = interpolate(frame, [REPLY, REPLY + 12], [0, 1], { ...clamp, easing: easeOut });

  return (
    <AbsoluteFill style={{ fontFamily: SANS }}>
      <GalatiqonCanvas width={width} height={height} devices={[dev]} cam={cam} />
      {/* press ripples around the button */}
      <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        {[0, 1, 2].map((k) => {
          const t = (frame - PRESS - k * 10) / 40;
          if (t < 0 || t > 1 || frame > RELEASE + 30) return null;
          return <ellipse key={k} cx={btn.x} cy={btn.y} rx={60 + t * 220} ry={(60 + t * 220) * 0.28} fill="none" stroke={C.accent} strokeWidth={2} opacity={(1 - t) * 0.8} />;
        })}
      </svg>
      <div style={{ position: "absolute", left: 120, top: 150, width: 860 }}>
        <Eyebrow delay={0}>How it works</Eyebrow>
        <div style={{ fontSize: 104, fontWeight: 500, color: C.white, letterSpacing: "-0.035em", lineHeight: 1.02, marginTop: 30 }}>
          <MaskedWords text="Hold the button." delay={6} />
          <br />
          <MaskedWords text="Ask the company." delay={20} highlight={["company"]} />
        </div>

        {/* the question */}
        <div style={{ marginTop: 64, opacity: qIn, transform: `translateY(${(1 - qIn) * 20}px)` }}>
          <div style={{ fontFamily: MONO, fontSize: 16, letterSpacing: "0.3em", color: "rgba(255,255,255,0.5)", marginBottom: 14, display: "flex", gap: 16, alignItems: "center" }}>
            YOU · HOLDING {frame >= PRESS && frame < RELEASE && <Eq h={18} bars={4} color={C.accent} />}
          </div>
          <div style={{ display: "inline-block", padding: "20px 30px", borderRadius: 24, border: `1px solid ${C.hair}`, background: "rgba(255,255,255,0.04)", fontSize: 38, color: C.white }}>
            “{typed(Q, frame, PRESS + 4, 0.55)}
            {frame < RELEASE && frame % 16 < 8 ? "|" : ""}
            {typed(Q, frame, PRESS + 4, 0.55).length === Q.length ? "”" : ""}
          </div>
        </div>

        {/* sources lighting up */}
        <div style={{ display: "flex", gap: 12, marginTop: 34, flexWrap: "wrap", alignItems: "center" }}>
          {frame >= RELEASE &&
            SOURCES.map((s, i) => (
              <Chip key={s} delay={RELEASE + i * 6} active={frame < REPLY ? srcIn(i) * (0.5 + 0.5 * Math.sin((frame - i * 5) / 4)) : 0} style={{ fontSize: 17, padding: "9px 18px" }}>
                {s}
              </Chip>
            ))}
          {frame >= RELEASE && (
            <div style={{ fontFamily: MONO, fontSize: 18, color: C.accent, marginLeft: 10, opacity: srcIn(0) }}>{timer.toFixed(1)} s</div>
          )}
        </div>

        {/* the spoken answer */}
        <div style={{ marginTop: 40, opacity: aIn, transform: `translateY(${(1 - aIn) * 20}px)` }}>
          <div style={{ fontFamily: MONO, fontSize: 16, letterSpacing: "0.3em", color: C.accent, marginBottom: 14 }}>GROK BOT · SPOKEN</div>
          <div style={{ fontSize: 46, fontWeight: 500, color: C.white, lineHeight: 1.25 }}>
            {typed(A1, frame, REPLY, 0.8)}
            <br />
            <span style={{ color: C.grey }}>{typed(A2, frame, REPLY + 70, 0.8)}</span>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
