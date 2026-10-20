import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { ContactShadows, Environment, Float, Lightformer, OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { MARK_PATHS, MARK_VIEWBOX } from '../lib/brand'

const MODEL = '/models/galatiqon.glb'
const S = 10 // the GLB is in metres; the scene works in decimetres (device ~1.1 wide).
// Everything inside the scaled group below is therefore in METRES.

// From enclosure/galatiqon.py (mm): face at Z = 58, screen window centre y = -30, G mark at (-31, 24).
const D = 0.058
const SCREEN_Y = -0.030
const LOGO = { x: -0.031, y: 0.024, ro: 0.0115, ri: 0.007 }

const PHRASES = [
  'Tom is free at 3.',
  'Scott wants the deck by Friday.',
  'Pipeline review moved to 10.',
  'Barric merged the CRM sync.',
  'Two new leads from Austin.',
]

const TEAL = '#13b37f'   // between the product render's mint and Galatiq's #009a6c
const TEAL_DARK = '#0f9469'

function useTextTexture(draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void, w: number, h: number, deps: unknown[]) {
  return useMemo(() => {
    const c = document.createElement('canvas')
    c.width = w; c.height = h
    const ctx = c.getContext('2d')!
    draw(ctx, w, h)
    const t = new THREE.CanvasTexture(c)
    t.colorSpace = THREE.SRGBColorSpace
    t.anisotropy = 8
    return t
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}

function useFontsReady() {
  const [ok, setOk] = useState(false)
  useEffect(() => { document.fonts?.ready.then(() => setOk(true)) }, [])
  return ok
}

function ScreenText({ phrase }: { phrase: string }) {
  const tick = useRef(0)
  const [frame, setFrame] = useState(0)
  const fonts = useFontsReady()
  useFrame((_, dt) => { tick.current += dt; if (tick.current > 0.12) { tick.current = 0; setFrame((f) => f + 1) } })
  const tex = useTextTexture((ctx, w, h) => {
    ctx.fillStyle = '#050607'; ctx.fillRect(0, 0, w, h)
    ctx.fillStyle = '#f3f6f4'
    ctx.font = '500 56px "Aventa", "Albert Sans", system-ui, sans-serif'
    ctx.textBaseline = 'middle'
    let text = phrase
    while (ctx.measureText(text).width > w - 230 && text.length > 4) text = text.slice(0, -2).trimEnd() + '…'
    ctx.fillText(text, 52, h / 2 + 2)
    const bx = w - 150
    for (let i = 0; i < 5; i++) {
      const hh = 14 + 34 * Math.abs(Math.sin(frame * 0.55 + i * 0.9))
      ctx.fillStyle = '#22d39a'
      const x = bx + i * 20
      ctx.beginPath(); ctx.roundRect(x, h / 2 - hh / 2, 9, hh, 4); ctx.fill()
    }
  }, 1024, 240, [phrase, frame, fonts])
  // window is 66 x 17 mm; the glass sits just behind the face wall
  return (
    <mesh position={[0, SCREEN_Y, D - 0.0095]}>  {/* inside the window cut, which starts 12.4 mm behind the face */}
      <planeGeometry args={[0.070, 0.0165]} />
      <meshBasicMaterial map={tex} toneMapped={false} />
    </mesh>
  )
}

function Mark() {
  const tex = useTextTexture((ctx, w, h) => {
    ctx.clearRect(0, 0, w, h)
    const [vx, vy, vw, vh] = MARK_VIEWBOX
    const k = Math.min(w / vw, h / vh)
    ctx.save(); ctx.translate((w - vw * k) / 2, (h - vh * k) / 2); ctx.scale(k, k); ctx.translate(-vx, -vy)
    ctx.fillStyle = '#f6f8f7'
    for (const d of MARK_PATHS) ctx.fill(new Path2D(d))
    ctx.restore()
  }, 512, 512, [])
  const size = LOGO.ro * 2.1
  return (
    <mesh position={[LOGO.x, LOGO.y, D - 0.0004]}>
      <planeGeometry args={[size, size]} />
      <meshBasicMaterial map={tex} transparent toneMapped={false} />
    </mesh>
  )
}

function Wordmark() {
  const fonts = useFontsReady()
  const tex = useTextTexture((ctx, w, h) => {
    ctx.clearRect(0, 0, w, h)
    ctx.fillStyle = '#063a28'
    ctx.font = '600 56px "Aventa", "Albert Sans", sans-serif'
    ctx.textBaseline = 'middle'; ctx.textAlign = 'center'
    ctx.letterSpacing = '26px'
    ctx.fillText('GALATIQON', w / 2 + 13, h / 2)
  }, 1024, 96, [fonts])
  return (
    <mesh position={[0, SCREEN_Y - 0.0118, D + 0.00015]}>
      <planeGeometry args={[0.048, 0.0045]} />
      <meshBasicMaterial map={tex} transparent toneMapped={false} />
    </mesh>
  )
}

function useMeshes() {
  const { scene } = useGLTF(MODEL)
  return useMemo(() => {
    const out: Record<string, THREE.BufferGeometry> = {}
    scene.traverse((o) => {
      const m = o as THREE.Mesh
      if (!m.isMesh) return
      const name = (m.name || m.geometry.name || '').toLowerCase()
      for (const key of ['body', 'face', 'button', 'pi', 'bank', 'screen']) {
        if (name.includes(key) && !out[key]) {
          if (!m.geometry.attributes.normal) m.geometry.computeVertexNormals() // trimesh exports no normals
          out[key] = m.geometry
        }
      }
    })
    return out
  }, [scene])
}

function Device({ exploded, phrase }: { exploded: boolean; phrase: string }) {
  const g = useMeshes()
  const faceRef = useRef<THREE.Group>(null)
  const btnRef = useRef<THREE.Group>(null)
  const ghostRef = useRef<THREE.Group>(null)
  const ghostMats = useRef<THREE.MeshPhysicalMaterial[]>([])

  const shell = useMemo(
    () => new THREE.MeshPhysicalMaterial({ color: TEAL, roughness: 0.55, metalness: 0, clearcoat: 0.3, clearcoatRoughness: 0.45, envMapIntensity: 0.7 }),
    [],
  )
  const cap = useMemo(() => new THREE.MeshPhysicalMaterial({ color: TEAL_DARK, roughness: 0.5, clearcoat: 0.35 }), [])
  const glass = useMemo(() => new THREE.MeshPhysicalMaterial({ color: '#050607', roughness: 0.25, clearcoat: 1 }), [])

  useFrame((_, dt) => {
    const k = 1 - Math.exp(-dt * 5)
    if (faceRef.current) faceRef.current.position.z += ((exploded ? 0.05 : 0) - faceRef.current.position.z) * k
    if (btnRef.current) btnRef.current.position.y += ((exploded ? 0.03 : 0) - btnRef.current.position.y) * k
    for (const m of ghostMats.current) m.opacity += ((exploded ? 0.85 : 0) - m.opacity) * k
    if (ghostRef.current) ghostRef.current.visible = ghostMats.current.some((m) => m.opacity > 0.02)
  })

  return (
    <group scale={S} position={[0, -0.02, -D * S / 2]}>
      {g.body && <mesh geometry={g.body} material={shell} castShadow receiveShadow />}

      <group ref={faceRef}>
        {g.face && <mesh geometry={g.face} material={shell} castShadow />}
        {/* screen: black glass behind the window, with the live line drawn on a canvas texture */}
        {g.screen && <mesh geometry={g.screen} material={glass} />}
        <ScreenText phrase={phrase} />
        <Wordmark />
        {/* the Galatiq G, inlaid white (drawn from the brand SVG paths) */}
        <Mark />
      </group>

      <group ref={btnRef}>{g.button && <mesh geometry={g.button} material={cap} castShadow />}</group>

      <group ref={ghostRef} visible={false}>
        {g.pi && (
          <mesh geometry={g.pi}>
            <meshPhysicalMaterial ref={(m) => { if (m && !ghostMats.current.includes(m)) ghostMats.current.push(m) }} color="#2f8f57" transparent opacity={0} roughness={0.7} />
          </mesh>
        )}
        {g.bank && (
          <mesh geometry={g.bank}>
            <meshPhysicalMaterial ref={(m) => { if (m && !ghostMats.current.includes(m)) ghostMats.current.push(m) }} color="#3a3f44" transparent opacity={0} roughness={0.6} />
          </mesh>
        )}
      </group>
    </group>
  )
}

export default function DeviceModel({ exploded, spin = true, onSpinChange, phrase: external }: {
  exploded: boolean
  spin?: boolean            // auto-rotate the device; dragging it turns the spin off via onSpinChange
  onSpinChange?: (spin: boolean) => void
  phrase?: string
}) {
  const [i, setI] = useState(0)
  const ox = 0
  useEffect(() => {
    if (external) return
    const t = setInterval(() => setI((n) => (n + 1) % PHRASES.length), 4200)
    return () => clearInterval(t)
  }, [external])
  const phrase = external ?? PHRASES[i]

  return (
    <Canvas shadows dpr={[1, 2]} camera={{ position: [2.4 + ox, 1.1, 3.4], fov: 30 }} gl={{ antialias: true, alpha: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.05 }} style={{ background: 'transparent' }}>
      <hemisphereLight args={['#dfe9e4', '#0b1a14', 0.55]} />
      <directionalLight position={[3, 5, 4]} intensity={1.3} castShadow shadow-mapSize={[2048, 2048]} shadow-bias={-0.0002} />
      <directionalLight position={[-4, 2, -3]} intensity={0.6} color="#9ff2d2" />
      <directionalLight position={[0, -2, 4]} intensity={0.25} />
      <Suspense fallback={null}>
        <group position={[ox, 0, 0]}>
          <Float speed={1.2} rotationIntensity={0.08} floatIntensity={0.25} floatingRange={[-0.02, 0.02]}>
            <Device exploded={exploded} phrase={phrase} />
          </Float>
          <ContactShadows position={[0, -0.56, 0]} opacity={0.6} scale={5} blur={2.2} far={1.5} color="#000" />
        </group>
        {/* a studio built from light panels, rendered locally: no HDR to download */}
        <Environment resolution={256} frames={1}>
          <Lightformer form="rect" intensity={2.2} position={[0, 4, 1]} scale={[6, 3, 1]} rotation-x={-Math.PI / 2} color="#f2fbf7" />
          <Lightformer form="rect" intensity={1.1} position={[-5, 1, 1]} scale={[1.5, 5, 1]} rotation-y={Math.PI / 2} color="#cfeee0" />
          <Lightformer form="rect" intensity={0.8} position={[5, 0, 2]} scale={[1.5, 4, 1]} rotation-y={-Math.PI / 2} color="#ffffff" />
          <Lightformer form="ring" intensity={0.5} position={[0, -3, 3]} scale={3} color="#24c78f" />
        </Environment>
      </Suspense>
      <OrbitControls target={[ox, 0, 0]} enablePan={false} enableZoom={false} minDistance={2.4} maxDistance={6} autoRotate={spin} autoRotateSpeed={0.5} minPolarAngle={0.6} maxPolarAngle={1.75} onStart={() => onSpinChange?.(false)} />
    </Canvas>
  )
}

useGLTF.preload(MODEL)
