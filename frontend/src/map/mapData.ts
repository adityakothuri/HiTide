import type { Case, DriverPublic, Reroute, SegmentState, Town, TurnAround } from '../data/types'
import { segmentIndex } from '../lib/geo'
import type { DroneWithTrail } from '../state/reducer'
import { caseSeverity } from '../state/cases'

type FC = GeoJSON.FeatureCollection

export const EMPTY: FC = { type: 'FeatureCollection', features: [] }

export function floodedFc(town: Town, segments: Record<string, SegmentState>): FC {
  const idx = segmentIndex(town)
  const features: GeoJSON.Feature[] = []
  for (const seg of Object.values(segments)) {
    const f = idx.get(seg.edge_id)
    if (f) features.push({ type: 'Feature', geometry: f.geometry, properties: { status: seg.status, depth: seg.depth_in } })
  }
  return { type: 'FeatureCollection', features }
}

export function hazardsFc(town: Town, turns: Record<string, TurnAround>): FC {
  const idx = segmentIndex(town)
  const features: GeoJSON.Feature[] = []
  for (const t of Object.values(turns)) {
    const f = idx.get(t.hazard_edge_id)
    if (f) features.push({ type: 'Feature', geometry: f.geometry, properties: { driver: t.driver_id } })
  }
  return { type: 'FeatureCollection', features }
}

export function reroutesFc(reroutes: Record<string, Reroute>): FC {
  return {
    type: 'FeatureCollection',
    features: Object.values(reroutes).map((r) => ({ type: 'Feature', geometry: r.route, properties: { driver: r.driver_id } })),
  }
}

export function driversFc(drivers: Record<string, DriverPublic>, caseDrivers: ReadonlySet<string>): FC {
  return {
    type: 'FeatureCollection',
    features: Object.values(drivers)
      .filter((d) => !caseDrivers.has(d.id))
      .map((d) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [d.lon, d.lat] },
        properties: { id: d.id, stopped: d.situation === 'stopped_in_water' },
      })),
  }
}

export function casesFc(cases: readonly Case[], selected: string | null): FC {
  return {
    type: 'FeatureCollection',
    features: cases.map((c) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [c.location.lon, c.location.lat] },
      properties: { id: c.id, severity: caseSeverity(c), selected: c.id === selected },
    })),
  }
}

export function trailsFc(drones: Record<string, DroneWithTrail>): FC {
  return {
    type: 'FeatureCollection',
    features: Object.values(drones)
      .filter((d) => d.trail.length > 1)
      .map((d) => ({ type: 'Feature', geometry: { type: 'LineString', coordinates: d.trail }, properties: { id: d.id } })),
  }
}

/** Bearing in degrees from a to b, for pointing the drone marker. */
export function bearing(a: [number, number], b: [number, number]): number {
  const k = Math.cos((a[1] * Math.PI) / 180)
  return (Math.atan2((b[0] - a[0]) * k, b[1] - a[1]) * 180) / Math.PI
}
