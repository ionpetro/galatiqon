import { useEffect, useRef } from 'react'

/* The particle wave from galatiq.ai's homepage, drawn on a 2D canvas: a few sheets of dots that
   ride layered sine waves and fade toward the edges. Cheap enough to run behind the 3D hero. */
export default function Waves({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const c = ref.current!
    const ctx = c.getContext('2d')!
    let raf = 0, w = 0, h = 0, dpr = 1
    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = c.clientWidth; h = c.clientHeight
      c.width = w * dpr; c.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const ro = new ResizeObserver(resize); ro.observe(c)
    const SHEETS = 10, COLS = 300
    const t0 = performance.now()
    const draw = (now: number) => {
      const t = (now - t0) / 1000
      ctx.clearRect(0, 0, w, h)
      for (let s = 0; s < SHEETS; s++) {
        const depth = s / (SHEETS - 1)              // 0 = front sheet
        const baseY = h * (0.38 + depth * 0.3)
        for (let i = 0; i <= COLS; i++) {
          const u = i / COLS
          const x = u * w
          const y = baseY
            + Math.sin(u * 6.2 + t * 0.55 + depth * 1.7) * h * 0.11 * (1 - depth * 0.4)
            + Math.sin(u * 13.1 - t * 0.9 + s) * h * 0.035
            + Math.cos(u * 2.3 + t * 0.3) * h * 0.06
          const edge = Math.sin(u * Math.PI)        // fade at left/right
          const a = (1.0 - depth * 0.7) * (0.3 + 0.7 * edge) * (0.6 + 0.4 * Math.sin(u * 9 + t * 1.3 + s))
          ctx.fillStyle = `rgba(${60 + depth * 10}, ${235 - depth * 90}, ${170 - depth * 50}, ${Math.max(0, a)})`
          const r = 2.1 - depth * 1.1
          ctx.fillRect(x, y, r, r)
        }
      }
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(raf); ro.disconnect() }
  }, [])
  return <canvas ref={ref} className={className} aria-hidden="true" />
}
