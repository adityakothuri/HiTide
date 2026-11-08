import { Pause, Play, RotateCcw, SkipBack, SkipForward } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { RiskFrame } from '../risk/grid'
import type { WxState } from '../wx/useWx'
import { wxClock, wxDay, wxZone } from '../wx/time'
import type { HistoryPoint } from '../region/useRegion'
import s from './TimeSlider.module.css'

const HOUR_MS = 3_600_000

/** The backend's July 4 replay: when it runs, the bar follows its clock instead of local playback. */
export interface ReplayControl {
  mode: 'replay' | 'live'
  setMode: (m: 'replay' | 'live') => Promise<void>
  /** Live mode: when the feeds were last read. */
  liveAt: number | null
  /** Live mode: each public feed's health, keyed by feed id. */
  feeds?: Record<string, { status: string; detail?: string | null; error?: string | null }>
  running: boolean
  start: () => Promise<void>
  reset: () => Promise<void>
}

/** Bottom time bar: play, step, scrub, NWS warning marks and risk frame marks. Arrow keys move one step (5 min). */
export function TimeSlider({ wx, riskFrames, replay, chart }: { wx: WxState; riskFrames?: readonly RiskFrame[]; replay?: ReplayControl; chart?: readonly HistoryPoint[] }) {
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const run = (fn: () => Promise<void>) => {
    setBusy(true)
    setFailed(false)
    fn().catch(() => setFailed(true)).finally(() => setBusy(false))
  }
  const following = replay?.running === true
  const live = replay?.mode === 'live'
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
      {replay && (
        <div className={s.replay}>
          <div className={s.modeSwitch} role="group" aria-label="Data">
            <button type="button" aria-pressed={replay.mode === 'replay'} disabled={busy} onClick={() => replay.mode !== 'replay' && run(() => replay.setMode('replay'))}>July 4 replay</button>
            <button type="button" aria-pressed={replay.mode === 'live'} disabled={busy} onClick={() => replay.mode !== 'live' && run(() => replay.setMode('live'))}>
              <span className={s.liveDot} aria-hidden="true" />Live now
            </button>
          </div>
          {replay.mode === 'live' ? null : replay.running ? (
            <button type="button" className={s.replayBtn} onClick={() => run(replay.reset)} disabled={busy}>
              <RotateCcw aria-hidden="true" />
              Reset
            </button>
          ) : (
            <button type="button" className={`${s.replayBtn} ${s.primary}`} onClick={() => run(replay.start)} disabled={busy}>
              <Play aria-hidden="true" />
              {busy ? 'Starting…' : 'Run July 4 replay'}
            </button>
          )}
          {failed && <span className={s.replayError} role="alert">Backend not reachable</span>}
        </div>
      )}
      {live && replay ? (
        <p className={s.liveNote}>
          <FeedsChip feeds={replay.feeds ?? {}} />
          Updated {replay.liveAt ? `${wxClock(replay.liveAt)} ${wxZone(replay.liveAt)}` : '…'}. Drones fly only during a flood warning.
        </p>
      ) : (<>
      {!following && (
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
      )}

      <output className={`${s.readout} num`} aria-live="off">{label}</output>

      <div className={`${s.track} ${chart ? s.withChart : ''}`}>
        {chart && <PeopleChart history={chart} range={[a, b]} />}
        <div className={s.lane}>
        <input
          type="range"
          className={s.range}
          min={a}
          max={b}
          step={source.stepMs}
          value={wx.t}
          onChange={(e) => wx.setT(Number(e.target.value))}
          disabled={following}
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
        {riskFrames && (
          <div className={s.frames} aria-hidden="true">
            {riskFrames
              .filter((f) => f.t >= a && f.t <= b)
              .map((f) => (
                <span key={f.id} className={s.frame} style={{ left: `${((f.t - a) / (b - a)) * 100}%` }} />
              ))}
          </div>
        )}
        <div className={s.ticks} aria-hidden="true">
          {ticks.map((tk) => (
            <span key={tk.ms} className={`${s.tick} num`} style={{ left: `${tk.pct}%` }}>{wxClock(tk.ms)}</span>
          ))}
        </div>
              </div>
      </div>

      </>)}
      <span className={s.mode}>{live ? 'Live' : following ? 'Replay running' : source.mode === 'replay' ? 'Replay, July 4, 2025' : 'Live'}</span>
    </div>
  )
}

const CHART_W = 1000
const CHART_H = 22

/** People in danger over the run, drawn above the scrubber: warning (amber) stacked under danger and critical (red). */
function PeopleChart({ history, range: [a, b] }: { history: readonly HistoryPoint[]; range: [number, number] }) {
  if (history.length < 2) return <div className={s.chart} aria-hidden="true" />
  const max = Math.max(1, ...history.map((h) => h.critical + h.danger + h.warning))
  const x = (t: number) => (((t - a) / (b - a)) * CHART_W).toFixed(1)
  const y = (v: number) => (CHART_H - (v / max) * CHART_H).toFixed(1)
  const area = (top: (h: HistoryPoint) => number) => {
    const first = history[0]
    const last = history[history.length - 1]
    return `M${x(first.t)},${CHART_H} ${history.map((h) => `L${x(h.t)},${y(top(h))}`).join(' ')} L${x(last.t)},${CHART_H} Z`
  }
  const peak = history.reduce((m, h) => Math.max(m, h.critical + h.danger), 0)
  return (
    <svg className={s.chart} viewBox={`0 0 ${CHART_W} ${CHART_H}`} preserveAspectRatio="none" role="img" aria-label={`People in danger over the replay, peak ${peak}`}>
      <path d={area((h) => h.critical + h.danger + h.warning)} fill="var(--sev-warning)" opacity={0.28} />
      <path d={area((h) => h.critical + h.danger)} fill="var(--sev-critical)" opacity={0.55} />
    </svg>
  )
}

const FEED_NAME: Record<string, string> = { usgs_gage: 'USGS river gauges', nws_alerts: 'NWS alerts', mrms: 'NOAA MRMS radar', lsr: 'NWS storm reports', nwps: 'NWS river forecasts' }

/** "5/5 live feeds OK"; hover lists each feed and what it reported. Unconfigured optional feeds are left out. */
function FeedsChip({ feeds }: { feeds: Record<string, { status: string; detail?: string | null; error?: string | null }> }) {
  const used = Object.entries(feeds).filter(([, f]) => f.status !== 'not_used')
  const ok = used.filter(([, f]) => f.status === 'ok').length
  const detail = used.map(([k, f]) => `${FEED_NAME[k] ?? k}: ${f.status === 'ok' ? f.detail ?? 'ok' : f.error ?? f.status}`).join('\n')
  const healthy = used.length > 0 && ok === used.length
  return (
    <span className={`${s.feedsChip} ${healthy ? '' : s.feedsWarn}`} title={detail || 'Waiting for the first read'} tabIndex={0}>
      <span className={s.liveDot} aria-hidden="true" />
      {used.length ? `${ok}/${used.length} live feeds ${healthy ? 'OK' : 'reporting'}` : 'Connecting to live feeds'}
    </span>
  )
}
