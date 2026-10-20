import { useEffect, useState } from 'react'
import DeviceModel from './components/DeviceModel'
import Live from './components/Live'
import Setup from './components/Setup'
import Waves from './components/Waves'

const NAV = [
  ['device', 'Device'],
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
  const [spin, setSpin] = useState(true)
  const [active, setActive] = useState<string>('device')

  useEffect(() => {
    const obs = new IntersectionObserver((es) => { for (const e of es) if (e.isIntersecting) setActive(e.target.id) }, { rootMargin: '-45% 0px -45% 0px' })
    for (const [id] of NAV) { const el = document.getElementById(id); if (el) obs.observe(el) }
    return () => obs.disconnect()
  }, [])

  return (
    <div className="studio min-h-screen">
      <header className="fixed top-0 inset-x-0 z-40 bg-black/70 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-5 md:px-8 h-16 flex items-center justify-between">
          <Logo />
          <nav className="flex items-center gap-7 text-sm">
            {NAV.map(([id, label]) => <a key={id} href={`#${id}`} className="nav-link" aria-current={active === id}>{label}</a>)}
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
              <a href="#live" className="btn-ghost">See it live</a>
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

      <footer className="border-t border-line">
        <div className="max-w-7xl mx-auto px-5 md:px-8 py-10 flex flex-wrap items-center justify-between gap-4 text-xs text-ink-faint">
          <Logo />
          <span>Built at the Grok Bot Hackathon, Austin, October 2026 · <a className="hover:text-ink" href="https://galatiq.ai" target="_blank" rel="noreferrer">galatiq.ai</a></span>
        </div>
      </footer>
    </div>
  )
}
