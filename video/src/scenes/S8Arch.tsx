import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Eyebrow, MaskedWords, Mark, clamp, easeInOut, easeOut } from "../components/ui";
import { C, MONO, SANS } from "../theme";

const NODES = [
  { k: "01", t: "Button + mic", s: "hold to talk" },
  { k: "02", t: "Raspberry Pi", s: "Vosk speech-to-text" },
  { k: "03", t: "gbd", s: "GrokBotCLI daemon" },
  { k: "04", t: "Grok Bot", s: "xAI cloud · your bot" },
];
const W = 330,
  H = 170,
  GAP = 110,
  X0 = (1920 - (4 * W + 3 * GAP)) / 2,
  Y = 560;

export const S8Arch: React.FC<{ dur: number }> = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cx = (i: number) => X0 + i * (W + GAP);
  const ret = interpolate(frame, [130, 165], [0, 1], { ...clamp, easing: easeInOut });
  const retPath = `M ${cx(3) + W / 2} ${Y + H} C ${cx(3) + W / 2} ${Y + H + 150}, ${cx(0) + W / 2} ${Y + H + 150}, ${cx(0) + W / 2} ${Y + H}`;
  return (
    <AbsoluteFill style={{ fontFamily: SANS }}>
      <div style={{ position: "absolute", left: 120, top: 130 }}>
        <Eyebrow delay={0}>How it's built</Eyebrow>
        <div style={{ fontSize: 96, fontWeight: 500, color: C.white, letterSpacing: "-0.035em", lineHeight: 1.04, marginTop: 28 }}>
          <MaskedWords text="No Grok Bot SDK." delay={6} />
          <br />
          <MaskedWords text="So we built the bridge." delay={26} highlight={["bridge"]} />
        </div>
      </div>
      <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
        {[0, 1, 2].map((i) => {
          const p = interpolate(frame, [60 + i * 14, 80 + i * 14], [0, 1], { ...clamp, easing: easeOut });
          const x1 = cx(i) + W,
            x2 = cx(i + 1),
            y = Y + H / 2;
          const pkt = ((frame - 100 - i * 6) % 40) / 40;
          return (
            <g key={i}>
              <line x1={x1} y1={y} x2={x1 + (x2 - x1) * p} y2={y} stroke="rgba(255,255,255,0.35)" strokeWidth={1.5} />
              {frame > 100 && <circle cx={x1 + (x2 - x1) * pkt} cy={y} r={5} fill={C.accent} opacity={Math.sin(pkt * Math.PI)} />}
              <path d={`M ${x2 - 10} ${y - 7} L ${x2} ${y} L ${x2 - 10} ${y + 7}`} stroke="rgba(255,255,255,0.6)" fill="none" strokeWidth={1.5} opacity={p} />
            </g>
          );
        })}
        <path d={retPath} stroke={C.accent} strokeWidth={2} fill="none" pathLength={1} strokeDasharray="0.006 0.008" strokeDashoffset={-frame * 0.002} opacity={ret} />
        <path d={retPath} stroke="transparent" fill="none" />
      </svg>
      {NODES.map((n, i) => {
        const s = spring({ frame: frame - 44 - i * 12, fps, config: { damping: 16, stiffness: 120 } });
        const cloud = i === 3;
        return (
          <div
            key={n.k}
            style={{
              position: "absolute",
              left: cx(i),
              top: Y,
              width: W,
              height: H,
              borderRadius: 24,
              border: `1px solid ${cloud ? "rgba(34,211,154,0.7)" : C.hair}`,
              background: cloud ? "rgba(23,145,106,0.2)" : "rgba(14,14,14,0.9)",
              padding: "26px 30px",
              boxSizing: "border-box",
              opacity: s,
              transform: `translateY(${(1 - s) * 50}px) scale(${0.92 + 0.08 * s})`,
              boxShadow: cloud ? `0 0 ${60 * s}px rgba(34,211,154,0.25)` : undefined,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: "0.3em", color: C.accent }}>{n.k}</div>
              {i === 0 && <Mark size={26} color={C.accent} />}
            </div>
            <div style={{ fontSize: 44, fontWeight: 500, color: C.white, marginTop: 18, fontFamily: i === 2 ? MONO : SANS }}>{n.t}</div>
            <div style={{ fontSize: 21, color: C.grey, marginTop: 6, fontWeight: 300 }}>{n.s}</div>
          </div>
        );
      })}
      <div style={{ position: "absolute", left: 0, right: 0, top: Y + H + 150, display: "flex", justifyContent: "center", opacity: ret }}>
        <div style={{ fontFamily: MONO, fontSize: 19, letterSpacing: "0.12em", color: C.white, background: C.black, padding: "8px 22px", border: `1px solid rgba(34,211,154,0.5)`, borderRadius: 999 }}>
          reply streams back → Piper voice → speaker · first words in ~3 s
        </div>
      </div>
    </AbsoluteFill>
  );
};
