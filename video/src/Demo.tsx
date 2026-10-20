import React from "react";
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame } from "remotion";
import { Wave } from "./components/Wave";
import { Shell } from "./components/Shell";
import { Logo, clamp } from "./components/ui";
import { C, MONO } from "./theme";
import { S1Logo } from "./scenes/S1Logo";
import { S2Problem } from "./scenes/S2Problem";
import { S3Hero } from "./scenes/S3Hero";
import { S4Exploded } from "./scenes/S4Exploded";
import { S5Ask } from "./scenes/S5Ask";
import { S6Bots } from "./scenes/S6Bots";
import { S7Dashboard } from "./scenes/S7Dashboard";
import { S8Arch } from "./scenes/S8Arch";
import { S9Outro } from "./scenes/S9Outro";

// [from, duration, label]
export const TIMELINE = {
  logo: [0, 150, "Galatiq"],
  idea: [140, 130, "The idea"],
  hero: [260, 340, "The device"],
  inside: [590, 220, "Inside"],
  ask: [800, 310, "Ask"],
  bots: [1100, 280, "Bot to bot"],
  live: [1370, 190, "Live"],
  build: [1550, 220, "The bridge"],
  outro: [1760, 190, "Galatiqon"],
} as const;
export const TOTAL = 1950;

type Key = keyof typeof TIMELINE;
const KEYS = Object.keys(TIMELINE) as Key[];

const Hud: React.FC = () => {
  const frame = useCurrentFrame();
  const vis = interpolate(frame, [150, 175, 1750, 1770], [0, 1, 1, 0], clamp);
  let idx = 0;
  KEYS.forEach((k, i) => {
    if (frame >= TIMELINE[k][0] + 6) idx = i;
  });
  const label = TIMELINE[KEYS[idx]][2];
  return (
    <AbsoluteFill style={{ opacity: vis, pointerEvents: "none" }}>
      <div style={{ position: "absolute", left: 64, top: 52, display: "flex", alignItems: "center", gap: 18 }}>
        <Logo height={22} />
        <div style={{ width: 1, height: 20, background: "rgba(255,255,255,0.25)" }} />
        <div style={{ fontFamily: MONO, fontSize: 14, letterSpacing: "0.4em", color: "rgba(255,255,255,0.6)" }}>GALATIQON</div>
      </div>
      <div style={{ position: "absolute", right: 64, top: 54, fontFamily: MONO, fontSize: 14, letterSpacing: "0.3em", color: "rgba(255,255,255,0.5)", textTransform: "uppercase" }}>
        <span style={{ color: C.accent }}>{String(idx + 1).padStart(2, "0")}</span> / 09 · {label}
      </div>
      <div style={{ position: "absolute", left: 64, right: 64, bottom: 44, height: 1, background: C.hair }}>
        <div style={{ height: 1, width: `${(frame / TOTAL) * 100}%`, background: C.accent }} />
      </div>
    </AbsoluteFill>
  );
};

const GlobalWave: React.FC = () => {
  const f = useCurrentFrame();
  const K = [0, 90, 150, 270, 300, 600, 620, 810, 830, 1110, 1130, 1380, 1400, 1560, 1580, 1770, 1800, 1950];
  const intensity = interpolate(f, K, [0, 1, 0.9, 0.7, 0.45, 0.45, 0.4, 0.4, 0.3, 0.3, 0.38, 0.38, 0.22, 0.22, 0.35, 0.35, 1, 1], clamp);
  const rise = interpolate(f, [0, 100], [0, 1], { ...clamp, easing: (t) => 1 - Math.pow(1 - t, 3) });
  const center = interpolate(f, K, [0.62, 0.62, 0.6, 0.6, 0.78, 0.78, 0.8, 0.8, 0.82, 0.82, 0.8, 0.8, 0.86, 0.86, 0.6, 0.6, 0.66, 0.66], clamp);
  return <Wave intensity={intensity} rise={rise} center={center} amp={1} />;
};

export const Demo: React.FC = () => {
  const render = (k: Key, node: React.ReactNode, enter: "wipe" | "rise" | "fade" | "none" = "wipe", exit = true) => {
    const [from, dur] = TIMELINE[k];
    return (
      <Sequence key={k} from={from} durationInFrames={dur} name={k}>
        <Shell dur={dur} enter={enter} exit={exit}>
          {node}
        </Shell>
      </Sequence>
    );
  };
  return (
    <AbsoluteFill style={{ background: C.ink }}>
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 120%, #06140f 0%, #000 60%)" }} />
      <GlobalWave />
      {render("logo", <S1Logo />, "none")}
      {render("idea", <S2Problem />, "fade")}
      {render("hero", <S3Hero dur={TIMELINE.hero[1]} />, "wipe")}
      {render("inside", <S4Exploded dur={TIMELINE.inside[1]} />, "wipe")}
      {render("ask", <S5Ask dur={TIMELINE.ask[1]} />, "rise")}
      {render("bots", <S6Bots dur={TIMELINE.bots[1]} />, "wipe")}
      {render("live", <S7Dashboard dur={TIMELINE.live[1]} />, "rise")}
      {render("build", <S8Arch dur={TIMELINE.build[1]} />, "wipe")}
      {render("outro", <S9Outro dur={TIMELINE.outro[1]} />, "fade", false)}
      <Hud />
    </AbsoluteFill>
  );
};
