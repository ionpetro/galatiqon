import React, { useEffect, useMemo, useState } from "react";
import { ThreeCanvas } from "@remotion/three";
import { continueRender, delayRender, staticFile, useCurrentFrame } from "remotion";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { MARK_PATHS, MARK_VIEWBOX } from "../brand";
import { SANS } from "../theme";

/* The GLB is in metres (Y up, face toward +Z, z 0..0.058). The device group scales x10 (decimetres)
   and recentres on z so the scene orbits around the middle of the puck. */
const S = 10;
const Z_OFF = -0.029 * S;
const D = 0.058;
const SCREEN_Y = -0.03;
const LOGO = { x: -0.031, y: 0.024, ro: 0.0115 };
const TEAL = "#13b37f";
const TEAL_DARK = "#0f9469";

export type ScreenState = { text: string; eq?: number; mode?: "text" | "listening" | "idle"; label?: string };
export type DeviceState = {
  position?: [number, number, number];
  rotY?: number;
  rotX?: number;
  rotZ?: number;
  scale?: number;
  explode?: number;
  press?: number;
  screen: ScreenState;
  glow?: number;
};
export type CameraState = { pos: [number, number, number]; target: [number, number, number]; fov: number };

// ---------- model loading (once, cached) ----------
type Geoms = Record<string, THREE.BufferGeometry>;
let cache: Promise<Geoms> | null = null;
const loadGeoms = () => {
  if (!cache)
    cache = new Promise<Geoms>((resolve, reject) => {
      new GLTFLoader().load(
        staticFile("galatiqon.glb"),
        (gltf) => {
          const out: Geoms = {};
          gltf.scene.traverse((o) => {
            const m = o as THREE.Mesh;
            if (!m.isMesh) return;
            const name = (m.name || m.geometry.name || "").toLowerCase();
            for (const key of ["body", "face", "button", "pi", "bank", "screen"]) {
              if (name.includes(key) && !out[key]) {
                // trimesh exports no normals: smooth them, keeping hard edges (> 40deg) crisp
                const geo = m.geometry.clone();
                geo.deleteAttribute("normal");
                out[key] = key === "pi" || key === "bank" ? (geo.computeVertexNormals(), geo) : toCreasedNormals(geo, (40 * Math.PI) / 180);
              }
            }
          });
          resolve(out);
        },
        undefined,
        reject,
      );
    });
  return cache;
};

const useGeoms = () => {
  const [g, setG] = useState<Geoms | null>(null);
  const [handle] = useState(() => delayRender("Loading galatiqon.glb"));
  useEffect(() => {
    loadGeoms()
      .then((x) => {
        setG(x);
        requestAnimationFrame(() => continueRender(handle));
      })
      .catch((e) => {
        console.error(e);
        continueRender(handle);
      });
  }, [handle]);
  return g;
};

// ---------- projection helper (for DOM callouts) ----------
export const projectPoint = (p: [number, number, number], dev: DeviceState, cam: CameraState, width: number, height: number, part?: "face" | "button") => {
  const explode = dev.explode ?? 0;
  const local = new THREE.Vector3(...p);
  if (part === "face") local.z += explode * 0.05;
  if (part === "button") local.y += explode * 0.03 - (dev.press ?? 0) * 0.004;
  local.multiplyScalar(S).add(new THREE.Vector3(0, 0, Z_OFF));
  const outer = new THREE.Matrix4().compose(
    new THREE.Vector3(...(dev.position ?? [0, 0, 0])),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(dev.rotX ?? 0, dev.rotY ?? 0, dev.rotZ ?? 0)),
    new THREE.Vector3().setScalar(dev.scale ?? 1),
  );
  local.applyMatrix4(outer);
  const camera = new THREE.PerspectiveCamera(cam.fov, width / height, 0.1, 100);
  camera.position.set(...cam.pos);
  camera.lookAt(new THREE.Vector3(...cam.target));
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();
  local.project(camera);
  return { x: ((local.x + 1) / 2) * width, y: ((1 - local.y) / 2) * height };
};

// ---------- textures ----------
const makeCanvasTexture = (w: number, h: number) => {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return { c, t };
};

const ScreenText: React.FC<{ s: ScreenState; seed: number }> = ({ s, seed }) => {
  const frame = useCurrentFrame();
  const { c, t } = useMemo(() => makeCanvasTexture(1024, 240), []);
  const ctx = c.getContext("2d")!;
  const w = c.width,
    h = c.height;
  ctx.fillStyle = "#050607";
  ctx.fillRect(0, 0, w, h);
  const mode = s.mode ?? "text";
  ctx.textBaseline = "middle";
  if (mode === "listening") {
    ctx.fillStyle = "#22d39a";
    ctx.beginPath();
    ctx.arc(70, h / 2, 12 + 4 * Math.sin(frame * 0.4), 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#cfcfcf";
    ctx.font = `500 54px ${SANS}`;
    ctx.fillText(s.text || "Listening…", 104, h / 2 + 2);
  } else {
    ctx.fillStyle = mode === "idle" ? "#8a8f8c" : "#f3f6f4";
    ctx.font = `500 56px ${SANS}`;
    let text = s.text;
    while (ctx.measureText(text).width > w - 250 && text.length > 4) text = text.slice(1);
    ctx.fillText(text, 52, h / 2 + 2);
  }
  const eq = s.eq ?? 0;
  const bx = w - 170;
  for (let i = 0; i < 6; i++) {
    const v = Math.abs(Math.sin(frame * 0.45 + i * 0.9 + seed) * Math.cos(frame * 0.13 + i * 1.3));
    const hh = 12 + 70 * v * eq;
    ctx.fillStyle = eq > 0.02 ? "#22d39a" : "#2a4c40";
    ctx.beginPath();
    ctx.roundRect(bx + i * 20, h / 2 - hh / 2, 10, hh, 5);
    ctx.fill();
  }
  t.needsUpdate = true;
  return (
    <mesh position={[0, SCREEN_Y, D - 0.0125]}>
      <planeGeometry args={[0.07, 0.0165]} />
      <meshBasicMaterial map={t} toneMapped={false} />
    </mesh>
  );
};

const MarkDecal: React.FC = () => {
  const t = useMemo(() => {
    const { c, t } = makeCanvasTexture(512, 512);
    const ctx = c.getContext("2d")!;
    const [vx, vy, vw, vh] = MARK_VIEWBOX;
    const k = Math.min(512 / vw, 512 / vh);
    ctx.translate((512 - vw * k) / 2, (512 - vh * k) / 2);
    ctx.scale(k, k);
    ctx.translate(-vx, -vy);
    ctx.fillStyle = "#f6f8f7";
    for (const d of MARK_PATHS) ctx.fill(new Path2D(d));
    return t;
  }, []);
  const size = LOGO.ro * 2.1;
  return (
    <mesh position={[LOGO.x, LOGO.y, D - 0.0004]}>
      <planeGeometry args={[size, size]} />
      <meshBasicMaterial map={t} transparent toneMapped={false} />
    </mesh>
  );
};

const Wordmark: React.FC = () => {
  const t = useMemo(() => {
    const { c, t } = makeCanvasTexture(1024, 96);
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#063a28";
    ctx.font = `600 56px ${SANS}`;
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    (ctx as unknown as { letterSpacing: string }).letterSpacing = "26px";
    ctx.fillText("GALATIQON", 512 + 13, 48);
    return t;
  }, []);
  return (
    <mesh position={[0, SCREEN_Y - 0.0118, D + 0.00015]}>
      <planeGeometry args={[0.048, 0.0045]} />
      <meshBasicMaterial map={t} transparent toneMapped={false} />
    </mesh>
  );
};

const shadowTex = (() => {
  let t: THREE.Texture | null = null;
  return () => {
    if (t) return t;
    const { c, t: tex } = makeCanvasTexture(256, 256);
    const ctx = c.getContext("2d")!;
    const g = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
    g.addColorStop(0, "rgba(0,0,0,0.85)");
    g.addColorStop(0.5, "rgba(0,0,0,0.4)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 256, 256);
    t = tex;
    return t;
  };
})();

// Raspberry Pi detailing on the PCB slab (pi: x ±0.0425, y -0.026..0.030, z 0.0244..0.026)
const PiDetail: React.FC<{ opacity: number }> = ({ opacity }) => {
  const parts: { p: [number, number, number]; s: [number, number, number]; c: string; m?: number }[] = [
    { p: [-0.005, 0.004, 0.0275], s: [0.014, 0.014, 0.0012], c: "#1a1a1a" },
    { p: [0.012, -0.006, 0.0272], s: [0.01, 0.008, 0.001], c: "#222" },
    { p: [0.0345, 0.012, 0.0335], s: [0.017, 0.013, 0.014], c: "#b9bec2", m: 0.8 },
    { p: [0.0345, -0.012, 0.0325], s: [0.017, 0.015, 0.012], c: "#b9bec2", m: 0.8 },
    { p: [-0.006, 0.0265, 0.0295], s: [0.05, 0.005, 0.006], c: "#111" },
    { p: [-0.03, -0.022, 0.0275], s: [0.008, 0.005, 0.003], c: "#c9cdd0", m: 0.8 },
  ];
  return (
    <group>
      {parts.map((x, i) => (
        <mesh key={i} position={x.p}>
          <boxGeometry args={x.s} />
          <meshStandardMaterial color={x.c} metalness={x.m ?? 0.1} roughness={0.4} transparent opacity={opacity} />
        </mesh>
      ))}
    </group>
  );
};

const Device: React.FC<{ g: Geoms; d: DeviceState; seed: number }> = ({ g, d, seed }) => {
  const explode = d.explode ?? 0;
  const press = d.press ?? 0;
  const glow = d.glow ?? 0;
  const shell = useMemo(
    () => new THREE.MeshPhysicalMaterial({ color: TEAL, roughness: 0.55, metalness: 0, clearcoat: 0.3, clearcoatRoughness: 0.45, envMapIntensity: 0.7 }),
    [],
  );
  const cap = useMemo(() => new THREE.MeshPhysicalMaterial({ color: TEAL_DARK, roughness: 0.5, clearcoat: 0.35 }), []);
  const glass = useMemo(() => new THREE.MeshPhysicalMaterial({ color: "#050607", roughness: 0.25, clearcoat: 1 }), []);
  cap.emissive.set("#22d39a");
  cap.emissiveIntensity = press * 0.6 + glow * 0.3;
  const inner = Math.min(1, explode * 1.5);
  return (
    <group position={d.position ?? [0, 0, 0]} rotation={[d.rotX ?? 0, d.rotY ?? 0, d.rotZ ?? 0]} scale={d.scale ?? 1}>
      <mesh position={[0, -0.535, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[1.9, 1.3]} />
        <meshBasicMaterial map={shadowTex()} transparent depthWrite={false} opacity={0.9} />
      </mesh>
      <group scale={S} position={[0, 0, Z_OFF]}>
        {g.body && <mesh geometry={g.body} material={shell} />}
        <group position={[0, 0, explode * 0.05]}>
          {g.face && <mesh geometry={g.face} material={shell} />}
          {g.screen && <mesh geometry={g.screen} material={glass} />}
          <ScreenText s={d.screen} seed={seed} />
          <Wordmark />
          <MarkDecal />
          {/* dark cavity behind the eye slots, like the render */}
          <mesh position={[0.034, 0.02, 0.046]}>
            <planeGeometry args={[0.03, 0.036]} />
            <meshBasicMaterial color="#04140e" />
          </mesh>
        </group>
        <group position={[0, explode * 0.03 - press * 0.004, 0]}>{g.button && <mesh geometry={g.button} material={cap} />}</group>
        {inner > 0.01 && (
          <group>
            {g.pi && (
              <mesh geometry={g.pi}>
                <meshStandardMaterial color="#1f7a4c" roughness={0.6} transparent opacity={inner} />
              </mesh>
            )}
            <PiDetail opacity={inner} />
            {g.bank && (
              <mesh geometry={g.bank}>
                <meshStandardMaterial color="#3a3f44" roughness={0.5} metalness={0.3} transparent opacity={inner} />
              </mesh>
            )}
          </group>
        )}
      </group>
    </group>
  );
};

const Env: React.FC = () => {
  const { gl, scene } = useThree();
  useMemo(() => {
    const pm = new THREE.PMREMGenerator(gl);
    scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    (scene as unknown as { environmentIntensity: number }).environmentIntensity = 0.3;
  }, [gl, scene]);
  return null;
};

const Cam: React.FC<{ cam: CameraState }> = ({ cam }) => {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  camera.position.set(...cam.pos);
  camera.fov = cam.fov;
  camera.near = 0.1;
  camera.far = 100;
  camera.updateProjectionMatrix();
  camera.lookAt(new THREE.Vector3(...cam.target));
  camera.updateMatrixWorld(true);
  return null;
};

const Scene: React.FC<{ devices: DeviceState[]; cam: CameraState }> = ({ devices, cam }) => {
  const g = useGeoms();
  return (
    <>
      <Cam cam={cam} />
      <Env />
      <hemisphereLight args={["#dfe9e4", "#0b1a14", 0.55]} />
      <directionalLight position={[3, 5, 4]} intensity={1.3} />
      <directionalLight position={[-4, 2, -3]} intensity={0.7} color="#9ff2d2" />
      <directionalLight position={[0, -2, 4]} intensity={0.25} />
      {g && devices.map((d, i) => <Device key={i} g={g} d={d} seed={i * 2.1} />)}
    </>
  );
};

export const GalatiqonCanvas: React.FC<{ width: number; height: number; devices: DeviceState[]; cam: CameraState; style?: React.CSSProperties }> = ({ width, height, devices, cam, style }) => {
  return (
    <ThreeCanvas
      width={width}
      height={height}
      style={{ position: "absolute", inset: 0, ...style }}
      gl={{ antialias: true, alpha: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.05, preserveDrawingBuffer: true }}
      camera={{ fov: cam.fov, position: cam.pos }}
      dpr={1}
    >
      <Scene devices={devices} cam={cam} />
    </ThreeCanvas>
  );
};
