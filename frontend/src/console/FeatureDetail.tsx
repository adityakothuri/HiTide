import { X } from 'lucide-react'
import type { Town } from '../data/types'
import { segmentIndex } from '../lib/geo'
import { CATEGORY_LABEL } from '../wx/category'
import type { GaugeReading, WxSnapshot } from '../wx/types'
import { wxClock } from '../wx/time'
import type { Feature } from './MapView'
import s from './FeatureDetail.module.css'

const SPARK_W = 296
const SPARK_H = 72
const THRESHOLDS = ['action', 'minor', 'moderate', 'major'] as const

function Sparkline({ g, t, range }: { g: GaugeReading; t: number; range: [number, number] }) {
  const pts = g.series.filter(([ms]) => ms >= range[0] && ms <= range[1])
  if (pts.length < 2) return <p className={s.muted}>No readings in this window.</p>
  const levels = g.categories ? THRESHOLDS.map((k) => g.categories![k]) : []
  const hi = Math.max(...pts.map(([, v]) => v), ...levels) * 1.05
  const lo = Math.min(0, ...pts.map(([, v]) => v))
  const x = (ms: number) => ((ms - range[0]) / (range[1] - range[0])) * SPARK_W
  const y = (v: number) => SPARK_H - ((v - lo) / (hi - lo)) * SPARK_H
  const path = pts.map(([ms, v], i) => `${i ? 'L' : 'M'}${x(ms).toFixed(1)},${y(v).toFixed(1)}`).join('')
  return (
    <svg className={s.spark} viewBox={`0 0 ${SPARK_W} ${SPARK_H}`} role="img" aria-label={`Stage from ${wxClock(range[0])} to ${wxClock(range[1])}`}>
      {g.categories && THRESHOLDS.map((k) => (
        <line key={k} x1={0} x2={SPARK_W} y1={y(g.categories![k])} y2={y(g.categories![k])} className={`${s.threshold} ${s[k]}`} />
      ))}
      <path d={path} className={s.series} />
      <line x1={x(t)} x2={x(t)} y1={0} y2={SPARK_H} className={s.cursor} />
    </svg>
  )
}

function GaugeBody({ g, t, range }: { g: GaugeReading; t: number; range: [number, number] }) {
  const cat = g.stageFt == null ? 'none' : g.category
  const trend = g.trendFtPerHr
  return (
    <>
      <p className={s.kicker}>USGS {g.site}</p>
      <h2 className={s.name}>{g.name}</h2>
      <div className={s.reading}>
        <span className={`${s.value} num`}>{g.stageFt == null ? 'No reading' : `${g.stageFt.toFixed(1)} ft`}</span>
        {trend != null && <span className={`${s.trend} num`}>{trend >= 0 ? '+' : '−'}{Math.abs(trend).toFixed(1)} ft/h</span>}
      </div>
      <p className={s.category}><span className={`${s.dot} ${s[cat]}`} />{CATEGORY_LABEL[cat]}</p>
      <Sparkline g={g} t={t} range={range} />
      {g.categories ? (
        <dl className={s.table}>
          {THRESHOLDS.map((k) => (
            <div key={k}><dt>{k[0].toUpperCase() + k.slice(1)}</dt><dd className="num">{g.categories![k]} ft</dd></div>
          ))}
        </dl>
      ) : (
        <p className={s.muted}>NWS has not set flood categories for this gauge.</p>
      )}
    </>
  )
}

function RoadBody({ edgeId, town, snap }: { edgeId: string; town: Town; snap: WxSnapshot }) {
  const name = segmentIndex(town).get(edgeId)?.properties.name || 'Unnamed road'
  const status = snap.roads.closed.has(edgeId) ? 'Closed, 6 in or more' : snap.roads.likely.has(edgeId) ? 'Likely flooded, 3 to 6 in' : 'Open at this time'
  return (
    <>
      <p className={s.kicker}>Road</p>
      <h2 className={s.name}>{name}</h2>
      <p className={s.reading}><span className={s.value}>{status}</span></p>
      <p className={s.muted}>Modelled from the Kerrville gauge and 10 m USGS terrain. Not a field report.</p>
    </>
  )
}

/** Right-hand panel for a clicked gauge or road. */
export function FeatureDetail({ feature, snap, town, range, onClose }: { feature: Feature; snap: WxSnapshot; town: Town | null; range: [number, number]; onClose: () => void }) {
  const gauge = feature.kind === 'gauge' ? snap.gauges.find((g) => g.site === feature.site) : null
  return (
    <aside className={s.panel} aria-label={feature.kind === 'gauge' ? 'Gauge detail' : 'Road detail'}>
      <button type="button" className={s.close} onClick={onClose} aria-label="Close">
        <X aria-hidden="true" />
      </button>
      {gauge && <GaugeBody g={gauge} t={snap.t} range={range} />}
      {feature.kind === 'road' && town && <RoadBody edgeId={feature.edgeId} town={town} snap={snap} />}
    </aside>
  )
}
