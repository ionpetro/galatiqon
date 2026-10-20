import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { GalatiqonCanvas, projectPoint, CameraState, DeviceState } from "../components/Device3D";
import { Callout } from "../components/Callout";
import { Chip, Eyebrow, MaskedWords, clamp, easeInOut, easeOut } from "../components/ui";
import { C, SANS } from "../theme";

type CP = { p: [number, number, number]; part: "face" | "button"; dx: number; dy: number; index: string; title: string; sub: string };
const CALLOUTS: CP[] = [
  { p: [0, 0.0526, 0.025], part: "button", dx: 330, dy: -60, index: "01 · BUTTON", title: "Push-to-talk", sub: "Hold, ask, let go" },
  { p: [-0.031, 0.024, 0.058], part: "face", dx: -330, dy: -70, index: "02 · MARK", title: "The Galatiq G", sub: "Inlaid on the face" },
  { p: [0.036, 0.02, 0.058], part: "face", dx: 300, dy: 30, index: "03 · EYES", title: "Two slanted eyes", sub: "It looks like it's listening" },
  { p: [0.036, -0.03, 0.058], part: "face", dx: 260, dy: 130, index: "04 · SCREEN", title: "Pill screen", sub: "The reply, live, with an equalizer" },
  { p: [-0.032, -0.047, 0.055], part: "face", dx: -300, dy: -20, index: "05 · MIC", title: "Microphone", sub: "Vosk speech-to-text, offline" },
  { p: [0, -0.048, 0.055], part: "face", dx: -360, dy: 120, index: "06 · SPEAKER", title: "Speaker grille", sub: "Piper voice, two sentences" },
];

export const S3Hero: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const enter = spring({ frame: frame - 4, fps, config: { damping: 18, stiffness: 60, mass: 1.2 } });
  const phase = interpolate(frame, [120, 160], [0, 1], { ...clamp, easing: easeInOut });
  const orbit = interpolate(frame, [0, 150], [-1.9, 0.38], { ...clamp, easing: easeOut });
  const drift = interpolate(frame, [150, dur], [0.38, 0.12], clamp);
  const rotY = frame < 150 ? orbit : drift;
  const dev: DeviceState = {
    position: [interpolate(phase, [0, 1], [-0.95, 0]), (1 - enter) * -2.4 + Math.sin(frame / 22) * 0.02, 0],
    rotY,
    rotX: (1 - enter) * 0.5,
    screen: { text: "Tom is free at 3.", eq: 0.7 },
  };
  const cam: CameraState = { pos: [0, interpolate(frame, [0, dur], [0.9, 0.35]), interpolate(frame, [0, dur], [5.4, 4.6])], target: [0, -0.02, 0], fov: 30 };
  const title = 1 - phase;
  const outC = interpolate(frame, [dur - 22, dur - 8], [0, 1], clamp);
  return (
    <AbsoluteFill>
      <GalatiqonCanvas width={width} height={height} devices={[dev]} cam={cam} />
      <div style={{ position: "absolute", left: 1080, top: 300, fontFamily: SANS, opacity: title, transform: `translateX(${(1 - title) * 80}px)` }}>
        <Eyebrow delay={20}>Meet the device</Eyebrow>
        <div style={{ fontSize: 168, fontWeight: 600, color: C.white, letterSpacing: "-0.04em", lineHeight: 1, marginTop: 30 }}>
          <MaskedWords text="Galatiqon" delay={26} />
        </div>
        <div style={{ fontSize: 36, fontWeight: 300, color: C.grey, marginTop: 24, maxWidth: 640, lineHeight: 1.3, opacity: interpolate(frame, [40, 60], [0, 1], clamp) }}>
          Your own Grok Bot, on your desk. It answers out loud.
        </div>
        <div style={{ display: "flex", gap: 14, marginTop: 44 }}>
          <Chip delay={52}>112 × 104 × 58 mm</Chip>
          <Chip delay={58}>3D-printed</Chip>
          <Chip delay={64}>Raspberry Pi inside</Chip>
        </div>
      </div>
      {frame >= 150 &&
        CALLOUTS.map((c, i) => {
          const a = projectPoint(c.p, dev, cam, width, height, c.part);
          return <Callout key={i} ax={a.x} ay={a.y} lx={a.x + c.dx} ly={a.y + c.dy} delay={158 + i * 16} index={c.index} title={c.title} sub={c.sub} out={outC} />;
        })}
    </AbsoluteFill>
  );
};
