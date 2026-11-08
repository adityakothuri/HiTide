import type { CSSProperties } from 'react'
import type { FloodCategory, RampLegend } from '../wx/types'
import type { WxState } from '../wx/useWx'
import { wxClock } from '../wx/time'
import s from './Colorbar.module.css'

const CATEGORIES: { key: FloodCategory; label: string }[] = [
  { key: 'action', label: 'Action' },
  { key: 'minor', label: 'Minor' },
  { key: 'moderate', label: 'Moderate' },
  { key: 'major', label: 'Major' },
  { key: 'below', label: 'Below' },
]

function Ramp({ legend }: { legend: RampLegend }) {
  const gradient = `linear-gradient(to right, ${legend.stops.map((st) => `${st.color} ${(st.pos * 100).toFixed(1)}%`).join(', ')})`
  return (
    <div className={s.ramp}>
      <div className={s.rampBar} style={{ background: gradient }} />
      <div className={s.rampTicks} aria-hidden="true">
        {legend.ticks.map((tk) => (
          <span key={tk.label} className={`${s.rampTick} num`} style={{ left: `${tk.pos * 100}%` }}>{tk.label}</span>
        ))}
      </div>
    </div>
  )
}

/** Always-visible key, bottom left. One block per enabled layer; every color on the map appears here. */
export function Colorbar({ wx }: { wx: WxState }) {
  const source = wx.load.status === 'ready' ? wx.load.source : null
  if (!source || !wx.snapshot) return null
  const { layers, snapshot } = wx
  const rain = layers.rain ? source.rain.products[layers.rain] : null
  const ticks = rain?.legend.ticks ?? []
  const rainSummary = ticks.length ? `${ticks[0].label} to ${ticks[ticks.length - 1].label}+ in` : ''

  return (
    <div className={s.box} role="group" aria-label="Map key">
      {rain && (
        <div className={s.block} aria-label={`Rainfall, ${rain.label}, ${rainSummary}`}>
          <p className={s.title}>
            Rainfall, {rain.label} <span className={s.unit}>in</span>
            {snapshot.rainValidAt != null && <span className={`${s.valid} num`}>ending {wxClock(snapshot.rainValidAt)}</span>}
          </p>
          <Ramp legend={rain.legend} />
        </div>
      )}
      {layers.depth && (
        <div className={s.block}>
          <p className={s.title}>Flood depth <span className={s.unit}>modelled</span></p>
          <ul className={s.steps}>
            {source.depthBands.map((b) => (
              <li key={b.label}><span className={s.swatch} style={{ background: b.color } as CSSProperties} />{b.label}</li>
            ))}
          </ul>
        </div>
      )}
      {layers.gauges && (
        <div className={s.block}>
          <p className={s.title}>Gauges <span className={s.unit}>NWS flood category</span></p>
          <ul className={s.steps}>
            {CATEGORIES.map((c) => (
              <li key={c.key}><span className={`${s.dot} ${s[c.key]}`} />{c.label}</li>
            ))}
          </ul>
        </div>
      )}
      {layers.roads && (
        <div className={s.block}>
          <p className={s.title}>Roads</p>
          <ul className={s.steps}>
            <li><span className={`${s.line} ${s.closed}`} />Closed, 6 in or more</li>
            <li><span className={`${s.line} ${s.likely}`} />Likely flooded</li>
          </ul>
        </div>
      )}
    </div>
  )
}
