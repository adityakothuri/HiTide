import type { RegionPick } from '../map/regionLayers'
import type { RegionState } from '../region/types'
import { DroneFleet, PointDetail, PointQueue } from './FleetPanel'
import s from './Console.module.css'

/** Right column on the monitor: the drone fleet, then the critical points it is working through. */
export function FleetPanel({ state, pointNames, pick, onPick }: { state: RegionState | null; pointNames: Record<string, string>; pick: RegionPick | null; onPick: (p: RegionPick | null) => void }) {
  const drones = state?.drones ?? []
  const points = state?.critical_points ?? []
  const picked = pick?.kind === 'point' ? points.find((p) => p.id === pick.id) ?? null : null
  return (
    <aside className={s.right} aria-label="Drones and critical points">
      {picked && <PointDetail point={picked} onClose={() => onPick(null)} />}
      <DroneFleet drones={drones} pointNames={pointNames} />
      <PointQueue points={points} pick={pick} onPick={onPick} />
    </aside>
  )
}
