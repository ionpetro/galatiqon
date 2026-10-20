/* Live data from the Galatiqon's Pi: galatiqon/dashboard.py serves /api/stats (JSON) and /events (SSE)
   on port 8080 with CORS. If the device cannot be reached, a simulated feed with the same shape runs
   so the page still shows what it will look like. */
import { useCallback, useEffect, useRef, useState } from 'react'

export type Snapshot = {
  t: number
  temp_c: number | null
  cpu_pct: number | null
  cores: number[]
  arm_mhz: number | null
  core_volts: number | null
  throttled: { raw: string; now: Record<string, boolean>; since_boot: Record<string, boolean> } | null
  undervolt_alarm: boolean | null
  mem: { total: number; used: number; swap_total: number; swap_used: number } | null
  disk: { total: number; used: number } | null
  wifi: { quality_pct: number; signal_dbm: number } | null
  wifi_info?: { ssid?: string | null; band?: string | null; channel?: string | null; rate?: string | null }
  net: { iface: string; rx_bps: number; tx_bps: number; rx_total: number; tx_total: number } | null
  uptime_s: number | null
  hostname: string
  ssid?: string | null
  ip?: string | null
  load?: number[] | null
  ncpu?: number
  services?: { unit: string; installed: boolean; active: string; sub: string; since: number | null }[]
  muse?: { state: string | null; label: string | null; state_t: number | null; events?: { t: number; level: string; msg: string; sys: boolean; n?: number }[]; error?: string }
  device?: { model?: string | null; os?: string | null; kernel?: string | null; arch?: string | null; serial?: string | null; ram_total?: number | null }
  procs?: { pid: number; name: string; user: string | null; cpu: number; rss: number }[]
  bluetooth?: { present: boolean; adapter?: { alias?: string; powered?: string } | null; devices?: { name: string; paired: boolean; connected: boolean }[] }
}

export type Point = { t: number; temp_c: number | null; cpu_pct: number | null; mem_pct: number | null; rx: number | null; tx: number | null; arm_mhz: number | null }
export type Mode = 'connecting' | 'live' | 'simulated' | 'offline'

export const DEFAULT_URL = 'http://galatiqon.local:8080'
const HISTORY = 300

export function toPoint(s: Snapshot): Point {
  return {
    t: s.t,
    temp_c: s.temp_c,
    cpu_pct: s.cpu_pct,
    mem_pct: s.mem?.total ? Math.round((1000 * s.mem.used) / s.mem.total) / 10 : null,
    rx: s.net?.rx_bps ?? null,
    tx: s.net?.tx_bps ?? null,
    arm_mhz: s.arm_mhz,
  }
}

// ---------------------------------------------------------------- simulation
function makeSimulator() {
  const boot = Date.now() / 1000 - 3 * 3600 - 912
  let temp = 46.5, cpu = 9, rx = 12_000, tx = 3_000, asked = 0
  const states = ['Ready', 'Listening', 'Thinking', 'Answering']
  let stateIdx = 0, stateAt = Date.now() / 1000
  const rnd = (a: number) => (Math.random() - 0.5) * a
  return (): Snapshot => {
    const t = Date.now() / 1000
    if (t - stateAt > (stateIdx === 0 ? 7 : stateIdx === 1 ? 3 : 4)) { stateIdx = (stateIdx + 1) % states.length; stateAt = t; if (stateIdx === 2) asked++ }
    const busy = stateIdx === 2 ? 55 : stateIdx === 3 ? 30 : 8
    cpu += (busy - cpu) * 0.25 + rnd(6); cpu = Math.max(1, Math.min(99, cpu))
    temp += (44 + cpu * 0.16 - temp) * 0.05 + rnd(0.3)
    rx = Math.max(500, rx + rnd(9000) + (stateIdx === 2 ? 40000 : 0) * 0.2); tx = Math.max(200, tx + rnd(2500))
    const cores = [0, 1, 2, 3].map(() => Math.max(0, Math.min(100, cpu + rnd(30))))
    const ev = (ago: number, msg: string, level = 'INFO') => ({ t: t - ago, level, msg, sys: false })
    return {
      t, temp_c: Math.round(temp * 10) / 10, cpu_pct: Math.round(cpu * 10) / 10, cores: cores.map((c) => Math.round(c)),
      arm_mhz: cpu > 20 ? 1500 : 600, core_volts: 0.86 + (cpu > 20 ? 0.03 : 0) + rnd(0.004),
      throttled: { raw: '0x0', now: { under_voltage: false, freq_capped: false, throttled: false, soft_temp_limit: false }, since_boot: { under_voltage: false, freq_capped: false, throttled: false, soft_temp_limit: false } },
      undervolt_alarm: false,
      mem: { total: 3_884_000_000, used: 611_000_000 + cpu * 2_000_000, swap_total: 104_857_600, swap_used: 0 },
      disk: { total: 125_000_000_000, used: 6_100_000_000 },
      wifi: { quality_pct: 78 + Math.round(rnd(4)), signal_dbm: -56 + Math.round(rnd(3)) },
      wifi_info: { ssid: 'galatiq-hq', band: '5 GHz', channel: '36', rate: '390 MBit/s' },
      net: { iface: 'wlan0', rx_bps: Math.round(rx), tx_bps: Math.round(tx), rx_total: 0, tx_total: 0 },
      uptime_s: t - boot, hostname: 'galatiqon', ssid: 'galatiq-hq', ip: '192.168.4.21', load: [0.4, 0.3, 0.3], ncpu: 4,
      services: [
        { unit: 'galatiqon-gbd', installed: true, active: 'active', sub: 'running', since: boot + 40 },
        { unit: 'galatiqon-output', installed: true, active: 'active', sub: 'running', since: boot + 31 },
        { unit: 'galatiqon-ptt', installed: true, active: 'active', sub: 'running', since: boot + 44 },
        { unit: 'galatiqon-dashboard', installed: true, active: 'active', sub: 'running', since: boot + 28 },
      ],
      muse: {
        state: stateIdx === 2 ? 'connecting' : 'connected', label: states[stateIdx], state_t: stateAt,
        events: [
          ev(t - boot - 40, 'listening on unix /home/galatiqon/.config/gb/default/gbd.sock'),
          ev(t - boot - 44, "talking to bot 'Galatiqon · Ion' via gbd"),
          ev(61 + asked * 0, "heard: 'is tom free at three'"),
          ev(57, 'reply after 3.4s: "Tom is free at 3."'),
          ev(12, "heard: 'what did scott want for friday'"),
          ev(9, 'reply after 2.9s: "Scott wants the deck by Friday."'),
        ],
      },
      device: { model: 'Raspberry Pi 4 Model B Rev 1.5', os: 'Debian GNU/Linux 12 (bookworm)', kernel: '6.6.51+rpt-rpi-v8', arch: 'aarch64', ram_total: 3_884_000_000 },
      procs: [
        { pid: 812, name: 'galatiqon-ptt', user: 'galatiqon', cpu: Math.round(cpu * 0.6), rss: 180_000_000 },
        { pid: 790, name: 'galatiqon-output', user: 'galatiqon', cpu: Math.round(cpu * 0.25), rss: 240_000_000 },
        { pid: 775, name: 'gb daemon', user: 'galatiqon', cpu: 1, rss: 22_000_000 },
      ],
      bluetooth: { present: true, adapter: { alias: 'galatiqon', powered: 'yes' }, devices: [] },
    }
  }
}

// ---------------------------------------------------------------- hook
export function useTelemetry(url: string) {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [history, setHistory] = useState<Point[]>([])
  const [mode, setMode] = useState<Mode>('connecting')
  const [gen, setGen] = useState(0)
  const simRef = useRef<ReturnType<typeof makeSimulator> | null>(null)

  const retry = useCallback(() => setGen((g) => g + 1), [])

  useEffect(() => {
    let es: EventSource | null = null
    let sim: ReturnType<typeof setInterval> | null = null
    let fallback: ReturnType<typeof setTimeout> | null = null
    let got = false
    let cancelled = false
    setMode('connecting'); setSnap(null); setHistory([])

    const push = (s: Snapshot) => {
      setSnap(s)
      setHistory((h) => [...h.slice(-(HISTORY - 1)), toPoint(s)])
    }
    const startSim = () => {
      if (cancelled || sim) return
      es?.close(); es = null
      simRef.current = makeSimulator()
      setMode('simulated')
      // seed a few minutes of history so the sparklines are not empty
      const seed: Point[] = []
      const now = Date.now() / 1000
      for (let i = 120; i > 0; i--) { const s = simRef.current(); s.t = now - i; seed.push(toPoint(s)) }
      setHistory(seed)
      push(simRef.current())
      sim = setInterval(() => push(simRef.current!()), 1000)
    }
    const base = url.replace(/\/+$/, '')
    // history first (fast when live), then the stream
    fetch(`${base}/api/history`, { cache: 'no-store' }).then((r) => r.json()).then((h: Point[]) => { if (!cancelled && Array.isArray(h) && !sim) setHistory(h.slice(-HISTORY)) }).catch(() => {})
    try {
      es = new EventSource(`${base}/events`)
      es.onmessage = (e) => {
        if (cancelled) return
        got = true
        if (fallback) { clearTimeout(fallback); fallback = null }
        setMode('live')
        try { push(JSON.parse(e.data)) } catch { /* ignore a bad frame */ }
      }
      es.onerror = () => { if (!got) startSim(); else setMode('offline') }
    } catch { startSim() }
    fallback = setTimeout(() => { if (!got) startSim() }, 3500)

    return () => { cancelled = true; es?.close(); if (sim) clearInterval(sim); if (fallback) clearTimeout(fallback) }
  }, [url, gen])

  return { snap, history, mode, retry }
}

export const fmtBytes = (b: number | null | undefined) => b == null ? '–' : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : b >= 1e6 ? `${(b / 1e6).toFixed(0)} MB` : `${(b / 1e3).toFixed(0)} KB`
export const fmtRate = (b: number | null | undefined) => b == null ? '–' : b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB/s` : b >= 1e3 ? `${(b / 1e3).toFixed(b >= 1e4 ? 0 : 1)} KB/s` : `${Math.round(b)} B/s`
export const fmtDur = (s: number | null | undefined) => { if (s == null) return '–'; s = Math.floor(s); const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60); return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m ${s % 60}s` }
export const ago = (t: number | null | undefined) => { if (!t) return '–'; const s = Math.max(0, Date.now() / 1000 - t); return s < 60 ? `${Math.floor(s)}s ago` : s < 3600 ? `${Math.floor(s / 60)} min ago` : `${Math.floor(s / 3600)} h ago` }
