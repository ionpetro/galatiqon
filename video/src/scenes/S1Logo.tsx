import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Eyebrow, Logo, clamp, easeInOut, easeOut, useSpring } from "../components/ui";
import { C, MONO } from "../theme";

export const S1Logo: React.FC = () => {
  const frame = useCurrentFrame();
  const mark = useSpring(8, { damping: 14, stiffness: 90 });
  const word = interpolate(frame, [34, 64], [0, 1], { ...clamp, easing: easeInOut });
  const glow = interpolate(frame, [8, 40, 120], [0, 1, 0.5], clamp);
  const drift = interpolate(frame, [0, 150], [1.04, 1], { easing: easeOut });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
      <div style={{ position: "absolute", width: 900, height: 900, borderRadius: "50%", background: "radial-gradient(circle, rgba(0,154,108,0.22) 0%, rgba(0,154,108,0) 60%)", opacity: glow }} />
      <div style={{ transform: `scale(${drift})`, display: "flex", flexDirection: "column", alignItems: "center", gap: 56 }}>
        <Logo height={150} markReveal={mark} reveal={word} />
        <div style={{ height: 30 }}>
          <Eyebrow delay={72} style={{ fontSize: 22 }}>
            Forward-deployed Grok agents
          </Eyebrow>
        </div>
      </div>
      <div style={{ position: "absolute", bottom: 80, fontFamily: MONO, fontSize: 16, letterSpacing: "0.4em", color: "rgba(255,255,255,0.4)", opacity: interpolate(frame, [90, 110], [0, 1], clamp) }}>
        GALATIQ.AI
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: "50%", height: 1, background: C.hair, transform: `scaleX(${interpolate(frame, [0, 40], [0, 1], { ...clamp, easing: easeOut })})`, opacity: 0.6, zIndex: -1 }} />
    </AbsoluteFill>
  );
};
