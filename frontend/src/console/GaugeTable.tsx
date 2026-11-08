import { CATEGORY_LABEL } from '../wx/category'
import type { FloodCategory, GaugeReading } from '../wx/types'
import type { Feature } from './MapView'
import s from './GaugeTable.module.css'

const RANK: Record<FloodCategory, number> = { major: 0, moderate: 1, minor: 2, action: 3, below: 4, none: 5 }
/** Under this, a change over the last hour reads as steady. */
const STEADY_FT_PER_HR = 0.1

function trendGlyph(ft: number | null): string {
  if (ft == null || Math.abs(ft) < STEADY_FT_PER_HR) return '–'
  return ft > 0 ? '▲' : '▼'
}

/** USGS station names, shortened to fit the panel ("North Fork Guadalupe Rv nr Hunt" -> "N Fk Guadalupe nr Hunt"). */
function shortName(name: string): string {
  return name.replace(/^North Fork /, 'N Fk ').replace(/ Rv\b/, '')
}

/** River gauges ranked by flood category, like an NWS observations table. A row opens the gauge. */
export function GaugeTable({ gauges, feature, onFeature }: { gauges: GaugeReading[]; feature: Feature | null; onFeature: (f: Feature) => void }) {
  const rows = [...gauges].sort((a, b) => RANK[a.category] - RANK[b.category] || (b.stageFt ?? -1) - (a.stageFt ?? -1))
  return (
    <section className={s.panel} aria-labelledby="gauges-h">
      <h2 id="gauges-h" className={s.heading}>
        River gauges <span className={s.unit}>stage, ft</span>
      </h2>
      <ul className={s.list}>
        {rows.map((g) => {
          const selected = feature?.kind === 'gauge' && feature.site === g.site
          return (
            <li key={g.site}>
              <button
                type="button"
                className={`${s.row} ${selected ? s.selected : ''}`}
                aria-pressed={selected}
                onClick={() => onFeature({ kind: 'gauge', site: g.site })}
                title={`${g.name}: ${CATEGORY_LABEL[g.category]}`}
              >
                <span className={`${s.dot} ${s[g.category]}`} aria-hidden="true" />
                <span className={s.name}>{shortName(g.name)}</span>
                <span className={`${s.stage} num`}>{g.stageFt != null ? g.stageFt.toFixed(1) : '—'}</span>
                <span className={`${s.trend} ${(g.trendFtPerHr ?? 0) >= STEADY_FT_PER_HR ? s.rising : ''}`} aria-label={g.trendFtPerHr != null ? `${g.trendFtPerHr.toFixed(1)} ft per hour` : 'no trend'}>
                  {trendGlyph(g.trendFtPerHr)}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
