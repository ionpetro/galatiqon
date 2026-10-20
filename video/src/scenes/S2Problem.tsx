import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Eyebrow, MaskedWords, clamp, easeOut } from "../components/ui";
import { C, SANS } from "../theme";

export const S2Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const line = interpolate(frame, [38, 70], [0, 1], { ...clamp, easing: easeOut });
  const sub = interpolate(frame, [52, 72], [0, 1], { ...clamp, easing: easeOut });
  const push = interpolate(frame, [0, 140], [0, -30]);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", fontFamily: SANS }}>
      <div style={{ transform: `translateY(${push}px)`, textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center" }}>
        <Eyebrow delay={0} style={{ marginBottom: 48 }}>
          The idea
        </Eyebrow>
        <div style={{ fontSize: 128, fontWeight: 500, color: C.white, lineHeight: 1.04, letterSpacing: "-0.03em" }}>
          <MaskedWords text="Your company's context," delay={6} stagger={4} />
        </div>
        <div style={{ position: "relative", fontSize: 128, fontWeight: 500, color: C.white, lineHeight: 1.04, letterSpacing: "-0.03em" }}>
          <MaskedWords text="one button away." delay={22} stagger={4} highlight={["one", "button", "away"]} />
          <div style={{ position: "absolute", left: 0, bottom: -10, height: 3, width: "100%", background: `linear-gradient(90deg, ${C.green}, ${C.accent})`, transformOrigin: "left", transform: `scaleX(${line})` }} />
        </div>
        <div style={{ marginTop: 60, fontSize: 36, fontWeight: 300, color: C.grey, opacity: sub, transform: `translateY(${(1 - sub) * 20}px)` }}>
          A push-to-talk desk device for every member of the Galatiq team.
        </div>
      </div>
    </AbsoluteFill>
  );
};
