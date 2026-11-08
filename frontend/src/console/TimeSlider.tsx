import { Pause, Play, SkipBack, SkipForward } from 'lucide-react'
import { useMemo } from 'react'
import type { WxState } from '../wx/useWx'
import { wxClock, wxDay, wxZone } from '../wx/time'
import s from './TimeSlider.module.css'

const HOUR_MS = 3_600_000

/** Bottom time bar: play, step, scrub. Arrow keys on the slider move one step (5 min). */
export function TimeSlider({ wx }: { wx: WxState }) {
  const source = wx.load.status === 'ready' ? wx.load.source : null
  const ticks = useMemo(() => {
    if (!source) return []
    const [a, b] = source.range
    const first = Math.ceil(a / HOUR_MS) * HOUR_MS
    const out: { ms: number; pct: number }[] = []
    for (let ms = first; ms <= b; ms += HOUR_MS) out.push({ ms, pct: ((ms - a) / (b - a)) * 100 })
    return out
  }, [source])

  if (wx.load.status === 'error') {
    return (
      <div className={s.bar}>
        <p className={s.error} role="status">{wx.load.message}</p>
      </div>
    )
  }
  if (!source) return <div className={s.bar} aria-busy="true" />

  const [a, b] = source.range
  const label = `${wxDay(wx.t)}, ${wxClock(wx.t)} ${wxZone(wx.t)}`
  return (
    <div className={s.bar} role="group" aria-label="Time">
      <div className={s.buttons}>
        <button type="button" className={s.btn} onClick={() => wx.step(-1)} aria-label="Back 5 minutes" disabled={wx.t <= a}>
          <SkipBack aria-hidden="true" />
        </button>
        <button
          type="button"
          className={s.btn}
          onClick={() => {
            if (!wx.playing && wx.t >= b) wx.setT(a)
            wx.setPlaying(!wx.playing)
          }}
          aria-label={wx.playing ? 'Pause' : 'Play'}
        >
          {wx.playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
        </button>
        <button type="button" className={s.btn} onClick={() => wx.step(1)} aria-label="Forward 5 minutes" disabled={wx.t >= b}>
          <SkipForward aria-hidden="true" />
        </button>
      </div>

      <output className={`${s.readout} num`} aria-live="off">{label}</output>

      <div className={s.track}>
        <input
          type="range"
          className={s.range}
          min={a}
          max={b}
          step={source.stepMs}
          value={wx.t}
          onChange={(e) => wx.setT(Number(e.target.value))}
          aria-label="Replay time"
          aria-valuetext={label}
        />
        <div className={s.events} aria-hidden="true">
          {source.warnings
            .filter((w) => w.issuedAt >= a && w.issuedAt <= b)
            .map((w) => (
              <span
                key={w.issuedAt}
                className={`${s.event} ${/emergency/i.test(w.event) ? s.emergency : ''}`}
                style={{ left: `${((w.issuedAt - a) / (b - a)) * 100}%` }}
                title={`${w.event}, ${w.area} · ${wxClock(w.issuedAt)}`}
              />
            ))}
        </div>
        <div className={s.ticks} aria-hidden="true">
          {ticks.map((tk) => (
            <span key={tk.ms} className={`${s.tick} num`} style={{ left: `${tk.pct}%` }}>{wxClock(tk.ms)}</span>
          ))}
        </div>
      </div>

      <span className={s.mode}>{source.mode === 'replay' ? 'Replay' : 'Live'}</span>
    </div>
  )
}
