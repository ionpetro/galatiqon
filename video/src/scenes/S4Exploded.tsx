import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { GalatiqonCanvas, projectPoint, CameraState, DeviceState } from "../components/Device3D";
import { Callout } from "../components/Callout";
import { Chip, Eyebrow, MaskedWords, clamp, easeInOut } from "../components/ui";
import { C, SANS } from "../theme";

export const S4Exploded: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const explode = spring({ frame: frame - 24, fps, config: { damping: 20, stiffness: 70 } });
  const rotY = interpolate(frame, [0, dur], [0.25, 0.85], { easing: easeInOut });
  const dev: DeviceState = { position: [0.45, -0.12, 0], rotY, rotX: 0.08, explode, screen: { text: "Pipeline review moved to 10.", eq: 0.4 } };
  const cam: CameraState = { pos: [interpolate(frame, [0, dur], [0.5, 0.2]), 0.75, interpolate(frame, [0, dur], [5.0, 4.4])], target: [0.3, 0.0, 0], fov: 30 };
  const outC = interpolate(frame, [dur - 20, dur - 8], [0, 1], clamp);
  const pts: { p: [number, number, number]; part?: "face" | "button"; dx: number; dy: number; i: string; t: string; s: string; d: number }[] = [
    { p: [0, 0.0526, 0.025], part: "button", dx: 320, dy: -10, i: "PART 1", t: "Button cap", s: "Springs on a tactile switch", d: 60 },
    { p: [-0.04, 0.0, 0.0255], dx: -380, dy: 90, i: "INSIDE", t: "Raspberry Pi", s: "Vosk + Piper, fully offline", d: 76 },
    { p: [0.05, 0.035, 0.058], part: "face", dx: 150, dy: 250, i: "PART 2", t: "Face", s: "45° chamfer, prints flat", d: 92 },
    { p: [-0.05, -0.04, 0.02], dx: -300, dy: 130, i: "PART 3", t: "Body + battery", s: "Flat chamfered back", d: 108 },
  ];
  return (
    <AbsoluteFill>
      <GalatiqonCanvas width={width} height={height} devices={[dev]} cam={cam} />
      {pts.map((c, k) => {
        const a = projectPoint(c.p, dev, cam, width, height, c.part);
        return <Callout key={k} ax={a.x} ay={a.y} lx={a.x + c.dx} ly={a.y + c.dy} delay={c.d} index={c.i} title={c.t} sub={c.s} out={outC} />;
      })}
      <div style={{ position: "absolute", left: 120, top: 140, fontFamily: SANS }}>
        <Eyebrow delay={6}>Inside</Eyebrow>
        <div style={{ fontSize: 80, fontWeight: 500, color: C.white, letterSpacing: "-0.03em", lineHeight: 1.04, marginTop: 30 }}>
          <MaskedWords text="Three printed parts." delay={10} />
          <br />
          <MaskedWords text="One Pi inside." delay={22} highlight={["Pi"]} />
        </div>
        <div style={{ display: "flex", gap: 14, marginTop: 44, flexWrap: "wrap", maxWidth: 600 }}>
          <Chip delay={44}>Raspberry Pi</Chip>
          <Chip delay={50}>Vosk STT</Chip>
          <Chip delay={56}>Piper TTS</Chip>
        </div>
      </div>
    </AbsoluteFill>
  );
};
