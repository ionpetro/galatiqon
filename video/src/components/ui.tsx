import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { C, MONO, SANS } from "../theme";
import { LOGO_PATHS, MARK_PATHS } from "../brand";

export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);

export const useSpring = (delay = 0, config: Partial<{ damping: number; stiffness: number; mass: number }> = {}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping: 200, ...config } });
};

export const Eyebrow: React.FC<{ children: React.ReactNode; delay?: number; color?: string; style?: React.CSSProperties }> = ({ children, delay = 0, color = C.accent, style }) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame - delay, [0, 18], [0, 1], { ...clamp, easing: easeOut });
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, fontFamily: MONO, fontSize: 18, letterSpacing: "0.32em", textTransform: "uppercase", color, ...style }}>
      <div style={{ width: 36 * p, height: 1, background: color }} />
      <span style={{ clipPath: `inset(0 ${100 - p * 100}% 0 0)` }}>{children}</span>
    </div>
  );
};

/* Words rise out of a mask, staggered. */
export const MaskedWords: React.FC<{ text: string; delay?: number; stagger?: number; style?: React.CSSProperties; highlight?: string[]; highlightColor?: string }> = ({ text, delay = 0, stagger = 3, style, highlight = [], highlightColor = C.accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text.split(" ");
  return (
    <span style={{ display: "inline-block", ...style }}>
      {words.map((w, i) => {
        const s = spring({ frame: frame - delay - i * stagger, fps, config: { damping: 200, stiffness: 120 } });
        const hl = highlight.includes(w.replace(/[.,]/g, ""));
        return (
          <span key={i} style={{ display: "inline-block", overflow: "hidden", verticalAlign: "top", paddingBottom: "0.08em", marginBottom: "-0.08em" }}>
            <span style={{ display: "inline-block", transform: `translateY(${(1 - s) * 105}%)`, color: hl ? highlightColor : undefined }}>
              {w}
              {i < words.length - 1 ? " " : ""}
            </span>
          </span>
        );
      })}
    </span>
  );
};

export const Chip: React.FC<{ children: React.ReactNode; delay?: number; style?: React.CSSProperties; active?: number }> = ({ children, delay = 0, style, active = 0 }) => {
  const s = useSpring(delay, { damping: 18, stiffness: 160 });
  return (
    <div
      style={{
        position: "relative",
        padding: "12px 22px",
        borderRadius: 999,
        fontFamily: MONO,
        fontSize: 20,
        color: C.white,
        background: `rgba(23,145,106,${0.2 + active * 0.35})`,
        opacity: s,
        transform: `translateY(${(1 - s) * 24}px) scale(${0.9 + s * 0.1})`,
        boxShadow: active ? `0 0 ${40 * active}px rgba(34,211,154,${0.45 * active})` : undefined,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {/* 1px green gradient border */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: 999,
          padding: 1,
          background: "linear-gradient(120deg, rgba(34,211,154,0.9), rgba(0,154,108,0.2) 50%, rgba(34,211,154,0.7))",
          WebkitMask: "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
          WebkitMaskComposite: "xor",
          maskComposite: "exclude",
        }}
      />
      {children}
    </div>
  );
};

export const Pill: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div style={{ background: C.white, color: C.black, borderRadius: 999, padding: "16px 34px", fontFamily: SANS, fontWeight: 500, fontSize: 26, ...style }}>{children}</div>
);

export const Logo: React.FC<{ height?: number; reveal?: number; markReveal?: number; color?: string }> = ({ height = 60, reveal = 1, markReveal = 1, color = C.white }) => {
  const w = (height * 122) / 26;
  const wordPaths = LOGO_PATHS.filter((d) => !MARK_PATHS.includes(d));
  return (
    <svg width={w} height={height} viewBox="0 0 122 26" style={{ overflow: "visible" }}>
      <defs>
        <clipPath id="wordclip">
          <rect x={22} y={-5} width={102 * reveal} height={36} />
        </clipPath>
      </defs>
      <g style={{ transformOrigin: "12.9px 12.6px", transform: `scale(${0.4 + 0.6 * markReveal}) rotate(${(1 - markReveal) * -200}deg)`, opacity: Math.min(1, markReveal * 2) }}>
        {MARK_PATHS.map((d, i) => (
          <path key={i} d={d} fill={color} />
        ))}
      </g>
      <g clipPath="url(#wordclip)">
        {wordPaths.map((d, i) => (
          <path key={i} d={d} fill={color} />
        ))}
      </g>
    </svg>
  );
};

export const Mark: React.FC<{ size?: number; color?: string; style?: React.CSSProperties }> = ({ size = 40, color = C.white, style }) => (
  <svg width={size} height={size} viewBox="2 2 22 22" style={style}>
    {MARK_PATHS.map((d, i) => (
      <path key={i} d={d} fill={color} />
    ))}
  </svg>
);

/* Equalizer bars, frame-driven. */
export const Eq: React.FC<{ level?: number; bars?: number; h?: number; color?: string; seed?: number }> = ({ level = 1, bars = 5, h = 40, color = C.accent, seed = 0 }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: h * 0.16, height: h }}>
      {new Array(bars).fill(0).map((_, i) => {
        const v = 0.25 + 0.75 * Math.abs(Math.sin(frame * 0.33 + i * 0.9 + seed) * Math.cos(frame * 0.11 + i * 1.7));
        return <div key={i} style={{ width: h * 0.16, height: h * (0.2 + 0.8 * v * level), borderRadius: 99, background: color }} />;
      })}
    </div>
  );
};
