import { useState } from 'react'
import { DEFAULT_URL, ago, fmtBytes, fmtDur, fmtRate, useTelemetry, type Point, type Snapshot } from '../lib/telemetry'

function Spark({ data, k, color = '#22d39a', max, min = 0, height = 44 }: { data: Point[]; k: keyof Point; color?: string; max?: number; min?: number; height?: number }) {
  const vals = data.map((p) => (p[k] as number | null) ?? null)
  const nums = vals.filter((v): v is number => v != null)
  if (nums.length < 2) return <div style={{ height }} className="w-full rounded bg-white/[0.02]" />
  const hi = max ?? (Math.max(...nums) * 1.08 || 1)
  const lo = min ?? Math.min(...nums)
  const w = 240
  const pts = vals.map((v, i) => (v == null ? null : [(i / (vals.length - 1)) * w, height - ((v - lo) / (hi - lo || 1)) * (height - 4) - 2] as const))
  let d = ''
  for (const p of pts) { if (!p) continue; d += (d ? ' L' : 'M') + `${p[0].toFixed(1)} ${p[1].toFixed(1)}` }
  const last = pts[pts.length - 1]
  return (
    <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
      <defs>
        <linearGradient id={`g-${String(k)}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.35" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {d && <path d={`${d} L ${w} ${height} L 0 ${height} Z`} fill={`url(#g-${String(k)})`} />}
      {d && <path d={d} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />}
      {last && <circle cx={last[0]} cy={last[1]} r="2.5" fill={color} />}
    </svg>
  )
}

function Card({ title, right, children, className = '' }: { title: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={`card p-5 flex flex-col gap-3 ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="eyebrow">{title}</div>
        {right && <div className="mono text-[11px] text-ink-dim">{right}</div>}
      </div>
      {children}
    </div>
  )
}

function Big({ v, unit, sub }: { v: string; unit?: string; sub?: string }) {
  return (
    <div>
      <div className="display text-3xl md:text-4xl font-light leading-none">
        {v}
        {unit && <span className="text-base text-ink-dim ml-1.5 font-sans">{unit}</span>}
      </div>
      {sub && <div className="text-xs text-ink-dim mt-2">{sub}</div>}
    </div>
  )
}

function Flag({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={`pill ${on ? 'border-rose text-rose' : 'text-ink-dim'}`}>
      <span className={`dot mr-1.5 ${on ? 'off' : ''}`} style={!on ? { background: '#2b3330' } : undefined} />
      {label}
    </span>
  )
}

const LINK_COLOR: Record<string, string> = { connected: 'live', paired: 'live', connecting: 'sim', starting: 'sim', unpaired: 'off' }

function botLabel(s: Snapshot) {
  const svc = s.services?.find((x) => x.unit === 'galatiqon-gbd')
  if (svc && svc.active !== 'active') return { cls: 'off', text: svc.installed ? 'Daemon stopped' : 'Not installed' }
  const m = s.muse
  if (!m?.state) return { cls: 'sim', text: 'Unknown' }
  return { cls: LINK_COLOR[m.state] ?? 'sim', text: m.label ?? m.state }
}

export default function Live() {
  const [url, setUrl] = useState(() => { try { return localStorage.getItem('galatiqon.url') || DEFAULT_URL } catch { return DEFAULT_URL } })
  const [draft, setDraft] = useState(url)
  const { snap: s, history, mode, retry } = useTelemetry(url)
  const apply = () => { const u = draft.trim() || DEFAULT_URL; setUrl(u); setDraft(u); try { localStorage.setItem('galatiqon.url', u) } catch { /* private window */ } }

  const thrNow = s?.throttled?.now ?? {}
  const thrBoot = s?.throttled?.since_boot ?? {}
  const memPct = s?.mem?.total ? Math.round((100 * s.mem.used) / s.mem.total) : null
  const bot = s ? botLabel(s) : null
  const modeText = mode === 'live' ? 'Live from the Pi' : mode === 'simulated' ? 'Simulated · no device reachable' : mode === 'offline' ? 'Stream dropped' : 'Connecting…'
  const modeCls = mode === 'live' ? 'live' : mode === 'simulated' ? 'sim' : mode === 'offline' ? 'off' : 'sim'

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col md:flex-row md:items-center gap-3 justify-between">
        <div className="flex items-center gap-3">
          <span className={`dot ${modeCls}`} />
          <span className="mono text-xs tracking-wider text-ink-dim uppercase">{modeText}</span>
          {mode !== 'live' && <button onClick={retry} className="pill hover:border-mint hover:text-mint transition">retry</button>}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); apply() }} className="flex items-center gap-2">
          <label className="mono text-[11px] text-ink-faint tracking-wider">DEVICE</label>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false}
            className="mono text-xs bg-bg-2 border border-line rounded-lg px-3 py-1.5 w-64 focus:outline-none focus:border-mint/60" />
          <button className="pill hover:border-mint hover:text-mint transition" type="submit">connect</button>
        </form>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <Card title="Device" right={s?.hostname} className="xl:col-span-2">
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <div><div className="text-ink-faint text-xs mb-0.5">Model</div><div>{s?.device?.model ?? '–'}</div></div>
            <div><div className="text-ink-faint text-xs mb-0.5">OS</div><div>{s?.device?.os ?? '–'} <span className="text-ink-dim">{s?.device?.arch}</span></div></div>
            <div><div className="text-ink-faint text-xs mb-0.5">Uptime</div><div className="mono">{fmtDur(s?.uptime_s)}</div></div>
            <div><div className="text-ink-faint text-xs mb-0.5">Address</div><div className="mono">{s?.ip ?? '–'} <span className="text-ink-dim">· {s?.ssid ?? s?.wifi_info?.ssid ?? '–'}</span></div></div>
          </div>
        </Card>

        <Card title="Grok Bot link" right={s?.muse?.state_t ? ago(s.muse.state_t) : undefined} className="xl:col-span-2">
          <div className="flex items-center gap-3">
            <span className={`dot ${bot?.cls ?? 'sim'}`} />
            <div className="display text-2xl font-light">{bot?.text ?? '–'}</div>
          </div>
          <ul className="mono text-[11.5px] leading-relaxed text-ink-dim max-h-28 overflow-hidden">
            {(s?.muse?.events ?? []).slice(-5).map((e, i) => (
              <li key={i} className="flex gap-3 truncate"><span className="text-ink-faint shrink-0">{ago(e.t)}</span><span className={e.level === 'ERROR' ? 'text-rose' : e.level === 'WARNING' ? 'text-amber' : ''}>{e.msg}{e.n && e.n > 1 ? ` ×${e.n}` : ''}</span></li>
            ))}
            {s?.muse?.error && <li className="text-amber">{s.muse.error}</li>}
          </ul>
        </Card>

        <Card title="Temperature" right={s?.arm_mhz ? `${s.arm_mhz} MHz` : undefined}>
          <Big v={s?.temp_c != null ? s.temp_c.toFixed(1) : '–'} unit="°C" sub={s?.temp_c != null ? (s.temp_c > 80 ? 'Hot: the SoC will throttle at 85 °C' : s.temp_c > 65 ? 'Warm, still fine' : 'Cool') : undefined} />
          <Spark data={history} k="temp_c" min={30} max={90} />
        </Card>

        <Card title="CPU" right={s?.load ? `load ${s.load[0]}` : undefined}>
          <Big v={s?.cpu_pct != null ? s.cpu_pct.toFixed(0) : '–'} unit="%" />
          <div className="flex gap-1 h-8 items-end">
            {(s?.cores ?? []).map((c, i) => <div key={i} className="flex-1 rounded-sm bg-mint/80" style={{ height: `${Math.max(6, c)}%`, opacity: 0.45 + c / 180 }} title={`core ${i}: ${c}%`} />)}
          </div>
          <Spark data={history} k="cpu_pct" min={0} max={100} />
        </Card>

        <Card title="Memory" right={s?.mem ? `${fmtBytes(s.mem.used)} / ${fmtBytes(s.mem.total)}` : undefined}>
          <Big v={memPct != null ? String(memPct) : '–'} unit="%" sub={s?.disk ? `Disk ${fmtBytes(s.disk.used)} of ${fmtBytes(s.disk.total)}` : undefined} />
          <Spark data={history} k="mem_pct" min={0} max={100} color="#7fe9c3" />
        </Card>

        <Card title="Power" right={s?.core_volts != null ? `${s.core_volts.toFixed(3)} V core` : undefined}>
          <Big v={Object.values(thrNow).some(Boolean) || s?.undervolt_alarm ? 'Problem' : s ? 'Good' : '–'} sub={Object.values(thrBoot).some(Boolean) ? 'Had a power event since boot' : 'No power events since boot'} />
          <div className="flex flex-wrap gap-1.5">
            <Flag on={!!thrNow.under_voltage} label="under-voltage" />
            <Flag on={!!thrNow.throttled} label="throttled" />
            <Flag on={!!thrNow.freq_capped} label="freq capped" />
            <Flag on={!!thrNow.soft_temp_limit} label="temp limit" />
          </div>
        </Card>

        <Card title="Network" right={s?.net?.iface}>
          <div className="grid grid-cols-2 gap-3">
            <div><div className="text-ink-faint text-xs">Down</div><div className="mono text-lg">{fmtRate(s?.net?.rx_bps)}</div></div>
            <div><div className="text-ink-faint text-xs">Up</div><div className="mono text-lg">{fmtRate(s?.net?.tx_bps)}</div></div>
          </div>
          <Spark data={history} k="rx" color="#7fe9c3" />
        </Card>

        <Card title="Wi-Fi" right={s?.wifi_info?.band ? `${s.wifi_info.band} · ch ${s.wifi_info.channel}` : undefined}>
          <Big v={s?.wifi ? String(s.wifi.quality_pct) : '–'} unit="%" sub={s?.wifi ? `${s.wifi.signal_dbm} dBm · ${s.wifi_info?.rate ?? ''}` : undefined} />
          <div className="h-1.5 rounded-full bg-white/5 overflow-hidden"><div className="h-full bg-mint rounded-full transition-all" style={{ width: `${s?.wifi?.quality_pct ?? 0}%` }} /></div>
        </Card>

        <Card title="Services" className="md:col-span-2">
          <ul className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            {(s?.services ?? []).map((sv) => (
              <li key={sv.unit} className="flex items-center gap-2.5">
                <span className={`dot ${sv.active === 'active' ? 'live' : sv.installed ? 'off' : 'sim'}`} />
                <span className="mono text-xs">{sv.unit}</span>
                <span className="text-ink-faint text-xs ml-auto">{sv.active === 'active' && sv.since ? `up ${fmtDur(Date.now() / 1000 - sv.since)}` : sv.sub}</span>
              </li>
            ))}
            {!s?.services?.length && <li className="text-ink-faint text-xs">–</li>}
          </ul>
        </Card>

        <Card title="Top processes" className="md:col-span-2">
          <ul className="text-sm">
            {(s?.procs ?? []).slice(0, 5).map((p) => (
              <li key={p.pid} className="flex items-center gap-3 py-1 border-b border-line last:border-0">
                <span className="mono text-xs text-ink-faint w-12">{p.pid}</span>
                <span className="truncate">{p.name}</span>
                <span className="mono text-xs text-ink-dim ml-auto">{p.cpu}% · {fmtBytes(p.rss)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}
