import { Crosshair, Navigation, X } from 'lucide-react'
import { droneName, pointTone } from '../region/derive'
import type { FleetDrone, RankedPoint } from '../region/types'
import type { RegionPick } from '../map/regionLayers'
import s from './Situation.module.css'

const KIND = { bridge: 'Bridge', crossing: 'Creek crossing', low_spot: 'Low spot' } as const
const POINT_STATUS = { confirmed_flooded: 'Flooded', likely_flooded: 'Likely flooded', unknown: 'Unconfirmed', open: 'Open' } as const
const NEXT_CHECKS = 5

/** Street names shortened for one-line rows: "Rio Vista Road South" -> "Rio Vista Rd S". */
function shortName(name: string): string {
  return name
    .replace(/\bRoad\b/g, 'Rd').replace(/\bStreet\b/g, 'St').replace(/\bHighway\b/g, 'Hwy').replace(/\bAvenue\b/g, 'Ave')
    .replace(/\bFarm-to-Market Rd\b/g, 'FM').replace(/\b(North|South|East|West)$/, (m) => m[0])
}

function droneAction(d: FleetDrone, names: Record<string, string>): string {
  const target = d.target ? shortName(names[d.target] ?? 'a crossing') : 'a crossing'
  if (d.status === 'flying') return `→ ${target}`
  if (d.status === 'snapshot') return `Checking ${target}`
  if (d.status === 'returning') return 'Returning'
  return 'At station'
}

/** The drone fleet, one line each: status, what it is doing, battery. */
export function DroneFleet({ drones, pointNames }: { drones: readonly FleetDrone[]; pointNames: Record<string, string> }) {
  return (
    <section className={s.section} aria-labelledby="fleet-h">
      <div className={s.head}>
        <h2 id="fleet-h" className={s.title}><Navigation className={`${s.titleIcon} ${s.iconDrone}`} aria-hidden="true" />Drones</h2>
        <span className={`${s.badge} ${s.badgeDrone}`}>{drones.filter((d) => d.status !== 'idle').length}/{drones.length} flying</span>
      </div>
      {drones.length === 0 ? (
        <p className={s.empty}>No drones reported.</p>
      ) : (
        <ul className={s.lines}>
          {drones.map((d) => (
            <li key={d.id} className={s.line} title={`${droneName(d)}, ${Math.round(d.km_flown)} km flown`}>
              <span className={`${s.dot} ${d.status === 'idle' ? '' : s.flying}`} aria-hidden="true" />
              <span className={s.name}>{droneName(d).replace(/ drone$/, '')}</span>
              <span className={s.lineMid}>{droneAction(d, pointNames)}</span>
              <span className={`${s.lineEnd} num`}>{Math.round(d.battery_pct)}%</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/** The next few critical points the drones will check, most useful first. */
export function PointQueue({ points, pick, onPick }: { points: readonly RankedPoint[]; pick: RegionPick | null; onPick: (p: RegionPick) => void }) {
  const top = points.slice(0, NEXT_CHECKS)
  return (
    <section className={s.section} aria-labelledby="points-h">
      <div className={s.head}>
        <h2 id="points-h" className={s.title}><Crosshair className={`${s.titleIcon} ${s.iconDrone}`} aria-hidden="true" />Next checks</h2>
        {points.some((p) => p.status === 'confirmed_flooded') && <span className={`${s.badge} ${s.badgeCritical}`}>{points.filter((p) => p.status === 'confirmed_flooded').length} flooded</span>}
      </div>
      {top.length === 0 ? (
        <p className={s.empty}>Nothing to check until a flood warning is active.</p>
      ) : (
        <ul className={s.list}>
          {top.map((p) => {
            const selected = pick?.kind === 'point' && pick.id === p.id
            const tone = pointTone(p.status)
            return (
              <li key={p.id}>
                <button type="button" className={`${s.row} ${selected ? s.on : ''}`} aria-pressed={selected} onClick={() => onPick({ kind: 'point', id: p.id })} title={`${KIND[p.kind]}${p.waterway ? `, ${p.waterway}` : ''}`}>
                  <span className={`${s.diamond} ${s[tone]}`} aria-hidden="true" />
                  <span className={s.name}>{shortName(p.name)}</span>
                  <span className={`${s.tag} ${s[tone]}`}>{POINT_STATUS[p.status]}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/** Why this point is on the list: who depends on it and how sure we are, from the backend's score breakdown. */
export function PointDetail({ point, onClose }: { point: RankedPoint; onClose: () => void }) {
  const b = point.breakdown
  const snap = point.last_snapshot
  return (
    <section className={`${s.section} ${s.detail}`} aria-labelledby="point-h">
      <div className={s.head}>
        <h2 id="point-h" className={s.title}>{point.name}</h2>
        <button type="button" className={s.close} onClick={onClose} aria-label="Close point detail"><X size={16} aria-hidden="true" /></button>
      </div>
      <p className={s.sub}>{KIND[point.kind]}{point.waterway ? ` over ${point.waterway}` : ''}</p>
      <dl className={s.facts}>
        <div><dt>Status</dt><dd>{POINT_STATUS[point.status]} <span className="num">({Math.round(point.p_flooded * 100)}% likely flooded)</span></dd></div>
        <div><dt>Depends on it</dt><dd className="num">{Math.round(b.dependency)} weighted homes, {point.node_ids.length} areas</dd></div>
        <div><dt>Vulnerability</dt><dd className="num">×{b.vulnerability.toFixed(2)}</dd></div>
        <div><dt>Uncertainty</dt><dd className="num">{Math.round(b.uncertainty * 100)}%</dd></div>
        {b.urgency > 1 && <div><dt>Urgent</dt><dd>Water forecast on the road within the hour</dd></div>}
        <div><dt>Last drone look</dt><dd>{snap ? (snap.water_on_road === true ? 'Water on the road' : snap.water_on_road === false ? 'Road looked dry (not a safety call)' : 'Road not visible') : 'Not checked yet'}</dd></div>
      </dl>
    </section>
  )
}
