import { useEffect, useState } from 'react'
import DeviceModel from './components/DeviceModel'
import Live from './components/Live'
import Setup from './components/Setup'
import Waves from './components/Waves'

const NAV = [
  ['device', 'Device'],
  ['demo', 'Demo'],
  ['live', 'Live'],
  ['setup', 'Setup'],
] as const

function Logo({ className = '' }: { className?: string }) {
  return (
    <a href="#device" className={`flex items-center gap-3 ${className}`} aria-label="Galatiqon">
      <img src="/galatiq-logo.svg" alt="Galatiq" className="h-[18px] w-auto" />
      <span className="h-4 w-px bg-white/20" />
      <span className="wordmark text-[11px] text-ink-dim">GALATIQON</span>
    </a>
  )
}

export default function App() {
  const [exploded, setExploded] = useState(false)
  const [demoOpen, setDemoOpen] = useState(false)
  const [spin, setSpin] = useState(true)
  const [active, setActive] = useState<string>('device')

  useEffect(() => {
    const obs = new IntersectionObserver((es) => { for (const e of es) if (e.isIntersecting) setActive(e.target.id) }, { rootMargin: '-45% 0px -45% 0px' })
    for (const [id] of NAV) { const el = document.getElementById(id); if (el) obs.observe(el) }
    return () => obs.disconnect()
  }, [])

  useEffect(() => {
    if (!demoOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setDemoOpen(false) }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [demoOpen])

  return (
    <div className="studio min-h-screen">
      <header className="fixed top-0 inset-x-0 z-40 bg-black/70 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-5 md:px-8 h-16 flex items-center justify-between">
          <Logo />
          <nav className="flex items-center gap-7 text-sm">
            {NAV.map(([id, label]) => <a key={id} href={`#${id}`} className="nav-link" aria-current={active === id}>{label}</a>)}
            <a href="https://github.com/ionpetro/galatiqon" target="_blank" rel="noreferrer" className="nav-link flex items-center gap-1.5" aria-label="GitHub repository">
              <svg viewBox="0 0 16 16" className="w-4 h-4" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>
              <span className="hidden md:inline">GitHub</span>
            </a>
            <a href="#setup" className="btn-white hidden md:inline-block !py-2 !px-4 text-[13px]">Build one</a>
          </nav>
        </div>
      </header>

      {/* -------------------------------------------------------------- hero */}
      <section id="device" className="relative min-h-screen pt-16 overflow-hidden">
        <Waves className="absolute inset-x-0 bottom-0 h-[70vh] w-full" />
        <div className="absolute inset-0 top-16 lg:left-[26%]">
          <DeviceModel exploded={exploded} spin={spin} onSpinChange={setSpin} />
        </div>
        <div className="relative max-w-7xl mx-auto px-5 md:px-8 pt-14 md:pt-24 pointer-events-none">
          <div className="max-w-xl fade-up">
            <h1 className="display text-5xl md:text-[64px] leading-[1.02]">
              Hold the button.<br />Ask the company.
            </h1>
            <p className="mt-6 text-ink-dim text-base md:text-lg max-w-md leading-relaxed">
              Each Galatiqon is wired to its owner's Grok Bot. It knows Galatiq, it's in the team's apps,
              and it can ask the other galatiqons. Answers come back spoken, in two sentences.
            </p>
            <div className="mt-8 flex items-center gap-3 pointer-events-auto">
              <a href="#setup" className="btn-white">Build one</a>
              <button type="button" onClick={() => setDemoOpen(true)} className="btn-ghost flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-white/10 grid place-items-center"><svg viewBox="0 0 10 10" className="w-2.5 h-2.5" fill="currentColor" aria-hidden="true"><path d="M2 1.2v7.6L8.4 5z" /></svg></span>
                Watch the demo
              </button>
            </div>
          </div>
        </div>
        <div className="absolute bottom-8 inset-x-0">
          <div className="max-w-7xl mx-auto px-5 md:px-8 flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-wrap gap-2 fade-up" style={{ animationDelay: '.25s' }}>
              {['112 × 104 × 58 mm', '3 printed parts', 'Raspberry Pi inside', 'offline speech-to-text', 'streams replies'].map((t) => <span key={t} className="pill">{t}</span>)}
            </div>
            <div className="flex items-center gap-2 fade-up" style={{ animationDelay: '.35s' }}>
              <button onClick={() => setExploded((e) => !e)} className={`pill transition ${exploded ? 'border-mint text-mint' : 'hover:border-mint hover:text-ink'}`}>
                {exploded ? 'assemble' : 'explode'}
              </button>
              <button onClick={() => setSpin((v) => !v)} className={`pill transition ${spin ? 'hover:border-mint hover:text-ink' : 'border-mint text-mint'}`} aria-pressed={!spin}>
                {spin ? 'stop spin' : 'spin'}
              </button>
              <span className="mono text-[11px] text-ink-faint hidden md:inline">drag to orbit</span>
            </div>
          </div>
        </div>
      </section>

      {/* a hairline frame strip, like the partner strip on galatiq.ai */}
      <div className="frame">
        <div className="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4">
          {[['Powered by', 'xAI Grok Bot'], ['Runs on', 'Raspberry Pi'], ['Speech', 'Vosk + Piper, offline'], ['Made in', 'Austin, Oct 2026']].map(([k, v]) => (
            <div key={k} className="frame-cell px-5 py-5">
              <div className="mono text-[10px] tracking-[0.2em] uppercase text-ink-faint">{k}</div>
              <div className="mt-1 text-sm">{v}</div>
            </div>
          ))}
        </div>
      </div>

      {/* -------------------------------------------------------------- demo */}
      <section id="demo" className="max-w-7xl mx-auto px-5 md:px-8 py-24">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
          <div>
            <div className="eyebrow mb-3">Demo · 65 seconds</div>
            <h2 className="display text-3xl md:text-[44px] leading-tight">See it work</h2>
          </div>
          <p className="text-sm text-ink-dim max-w-sm">The device, what's inside, a question and its spoken answer, two galatiqons talking, and the bridge to Grok Bot.</p>
        </div>
        <div className="relative rounded-2xl overflow-hidden border border-line bg-black shadow-[0_40px_120px_-40px_rgba(0,154,108,0.45)]">
          <video
            className="w-full aspect-video block"
            src="/galatiqon-demo.mp4"
            poster="/galatiqon-demo-poster.png"
            controls
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-ink-faint">
          <span>Rendered with Remotion from the same 3D model and brand assets as this page. No audio.</span>
          <a className="pill hover:border-mint hover:text-mint transition" href="/galatiqon-demo.mp4" download>download mp4</a>
        </div>
      </section>

      {/* -------------------------------------------------------------- live */}
      <section id="live" className="max-w-7xl mx-auto px-5 md:px-8 py-24">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-10">
          <div>
            <div className="eyebrow mb-3">Live · from the Raspberry Pi</div>
            <h2 className="display text-3xl md:text-[44px] leading-tight">What the device is doing right now</h2>
          </div>
          <p className="text-sm text-ink-dim max-w-sm">Power, heat, load, radio and the Grok Bot link, one sample a second over Server-Sent Events from the Pi's own dashboard.</p>
        </div>
        <Live />
      </section>

      {/* -------------------------------------------------------------- setup */}
      <section id="setup" className="max-w-7xl mx-auto px-5 md:px-8 py-24 border-t border-line">
        <div className="mb-12">
          <div className="eyebrow mb-3">Setup · build one</div>
          <h2 className="display text-3xl md:text-[44px] leading-tight">From a blank SD card to a talking Galatiqon</h2>
          <p className="text-sm text-ink-dim max-w-xl mt-4 leading-relaxed">
            Grok Bot has no public SDK, so the device talks through <a className="text-mint hover:underline" href="https://github.com/JiminLee-way/GrokBotCLI" target="_blank" rel="noreferrer">GrokBotCLI</a>'s
            headless daemon on the Pi. Everything else is offline on the device: speech-to-text, the voice, the screen.
          </p>
        </div>
        <Setup />
      </section>

      {demoOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-10 bg-black/85 backdrop-blur-md" onClick={() => setDemoOpen(false)} role="dialog" aria-modal="true" aria-label="Galatiqon demo video">
          <div className="relative w-full max-w-6xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <img src="/galatiq-logo.svg" alt="Galatiq" className="h-[14px] w-auto" />
                <span className="wordmark text-[10px] text-ink-dim">GALATIQON · DEMO</span>
              </div>
              <button type="button" onClick={() => setDemoOpen(false)} className="pill hover:border-mint hover:text-mint transition" aria-label="Close">close · esc</button>
            </div>
            <div className="rounded-2xl overflow-hidden border border-line bg-black shadow-[0_60px_160px_-40px_rgba(0,154,108,0.5)]">
              <video className="w-full aspect-video block" src="/galatiqon-demo.mp4" poster="/galatiqon-demo-poster.png" controls autoPlay playsInline />
            </div>
          </div>
        </div>
      )}

      <footer className="border-t border-line">
        <div className="max-w-7xl mx-auto px-5 md:px-8 py-10 flex flex-wrap items-center justify-between gap-4 text-xs text-ink-faint">
          <Logo />
          <span>Built at the Grok Bot Hackathon, Austin, October 2026 · <a className="hover:text-ink" href="https://galatiq.ai" target="_blank" rel="noreferrer">galatiq.ai</a></span>
        </div>
      </footer>
    </div>
  )
}
