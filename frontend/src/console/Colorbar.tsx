import { riskTicks } from '../risk/ticks'
import { turboCss } from '../risk/turbo'
import type { RampLegend } from '../wx/types'
import type { WxState } from '../wx/useWx'
import { wxClock } from '../wx/time'
import s from './Colorbar.module.css'

interface Props {
  wx: WxState
  /** Inside the Layers menu: no floating card, no footnote. */
  compact?: boolean
  /** Study area name from the risk grid index. */
  studyArea?: string
}

function Scale({ gradient, ticks, bands, label }: { gradient: string; ticks: { pos: number; label: string }[]; bands?: { pos: number; label: string }[]; label: string }) {
  return (
    <div className={s.scale} role="img" aria-label={label}>
      {bands && (
        <div className={s.bands} aria-hidden="true">
          {bands.map((b) => (
            <span key={b.label} className={s.band} style={{ left: `${b.pos * 100}%` }}>{b.label}</span>
          ))}
        </div>
      )}
      <div className={s.bar} style={{ background: `linear-gradient(to right, ${gradient})` }}>
        {ticks.slice(1, -1).map((t) => (
          <span key={t.label} className={s.notch} style={{ left: `${t.pos * 100}%` }} />
        ))}
      </div>
      <div className={s.ticks} aria-hidden="true">
        {ticks.map((t, i) => (
          <span
            key={t.label}
            className={`${s.tick} ${i === 0 ? s.first : i === ticks.length - 1 ? s.last : ''} num`}
            style={{ left: `${t.pos * 100}%` }}
          >
            {t.label}
          </span>
        ))}
      </div>
    </div>
  )
}

function rampGradient(legend: RampLegend): string {
  return legend.stops.map((st) => `${st.color} ${(st.pos * 100).toFixed(1)}%`).join(', ')
}

/** Legend for the active base field only, bottom left of the map: a horizontal colour bar with ticks. */
/** Map key: one pill strip, bottom left. Shapes say what a thing is, colour how bad it is. */
export function MapKey({ people = false }: { people?: boolean }) {
  return (
    <ul className={s.pill} aria-label="Map key">
      {people && <li><span className={s.pinKey} />Person</li>}
      <li><span className={`${s.sw} ${s.diamond}`} />Crossing</li>
      <li><span className={s.roadClosed} />Road closed</li>
      <li><span className={s.roadLikely} />Likely flooded</li>
      <li><span className={`${s.sw} ${s.ringKey}`} />Area cut off</li>
      <li>
        <svg className={s.droneKey} viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l6 16-6-4-6 4z" /></svg>
        Drone
      </li>
    </ul>
  )
}

export function Colorbar({ wx, studyArea, compact = false }: Props) {
  const source = wx.load.status === 'ready' ? wx.load.source : null
  if (!source || !wx.snapshot) return null
  const { layers, snapshot } = wx
  if (layers.base === 'none') return null
  const box = compact ? `${s.box} ${s.compact}` : s.box

  if (layers.base === 'risk') {
    const t = riskTicks()
    return (
      <div className={box} role="group" aria-label="Map key">
        <p className={s.title}>Flood risk index <span className={s.unit}>0 to 100</span></p>
        <Scale gradient={turboCss()} ticks={t.ticks} bands={t.bands} label="Flood risk index from 0, low, to 100, severe" />
        <p className={s.note}>Relative index, not water depth{studyArea ? `. ${studyArea}.` : '.'}</p>
      </div>
    )
  }

  if (layers.base === 'rain') {
    const rain = source.rain.products[layers.rainProduct]
    const ticks = rain.legend.ticks
    return (
      <div className={box} role="group" aria-label="Map key">
        <p className={s.title}>Rainfall, {rain.label} <span className={s.unit}>in</span></p>
        <Scale gradient={rampGradient(rain.legend)} ticks={ticks} label={`Rainfall ${rain.label}, ${ticks[0]?.label ?? ''} to ${ticks[ticks.length - 1]?.label ?? ''} inches`} />
        {snapshot.rainValidAt != null && <p className={`${s.note} num`}>Ending {wxClock(snapshot.rainValidAt)}. NOAA MRMS.</p>}
      </div>
    )
  }

  return (
    <div className={box} role="group" aria-label="Map key">
      <p className={s.title}>Flood depth <span className={s.unit}>modelled</span></p>
      <ul className={s.steps}>
        {[...source.depthBands].reverse().map((b) => (
          <li key={b.label}><span className={s.swatch} style={{ background: b.color }} />{b.label}</li>
        ))}
      </ul>
      <p className={s.note}>From river stage and 10 m terrain. Not a hydraulic model.</p>
    </div>
  )
}
