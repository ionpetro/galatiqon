import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Chip, Logo, MaskedWords, Pill, clamp, easeInOut, easeOut, useSpring } from "../components/ui";
import { C, MONO, SANS } from "../theme";

export const S9Outro: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const mark = useSpring(6, { damping: 14, stiffness: 90 });
  const word = interpolate(frame, [18, 44], [0, 1], { ...clamp, easing: easeInOut });
  const img = interpolate(frame, [0, 40], [0, 1], { ...clamp, easing: easeOut });
  const end = interpolate(frame, [dur - 18, dur], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ fontFamily: SANS }}>
      <div
        style={{
          position: "absolute",
          right: -120,
          top: 40,
          width: 1200,
          height: 1000,
          opacity: img,
          transform: `scale(${interpolate(frame, [0, dur], [1.12, 1.0])})`,
          WebkitMaskImage: "radial-gradient(ellipse 50% 52% at 50% 52%, #000 45%, transparent 100%)",
        }}
      >
        <Img src={staticFile("hero-render.png")} style={{ width: "100%", height: "100%", objectFit: "cover", filter: "brightness(0.95) contrast(1.08)" }} />
      </div>
      <div style={{ position: "absolute", left: 120, top: 250 }}>
        <Logo height={56} markReveal={mark} reveal={word} />
        <div style={{ fontSize: 176, fontWeight: 600, color: C.white, letterSpacing: "-0.045em", lineHeight: 1, marginTop: 40 }}>
          <MaskedWords text="Galatiqon" delay={30} />
        </div>
        <div style={{ fontSize: 40, fontWeight: 300, color: C.grey, marginTop: 24 }}>
          <MaskedWords text="Your company's context, one button away." delay={44} stagger={2} />
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 56, alignItems: "center" }}>
          <Chip delay={62}>Built at the Grok Bot Hackathon · Austin · Oct 2026</Chip>
        </div>
        <div style={{ display: "flex", marginTop: 34, opacity: interpolate(frame, [74, 90], [0, 1], clamp) }}>
          <Pill>galatiq.ai</Pill>
          <div style={{ fontFamily: MONO, fontSize: 17, color: "rgba(255,255,255,0.45)", letterSpacing: "0.25em", alignSelf: "center", marginLeft: 26 }}>POWERED BY GROK · xAI</div>
        </div>
      </div>
      <AbsoluteFill style={{ background: C.black, opacity: end }} />
    </AbsoluteFill>
  );
};
