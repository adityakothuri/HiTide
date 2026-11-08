import type { GeoJSONSource, Map as MlMap } from 'maplibre-gl'
import { areaTone, personTone, pointTone, type Tone } from '../region/derive'
import type { Area, FleetDrone, FloodRoad, MapPoint, Person, RegionInfo } from '../region/types'
import { EMPTY } from './mapData'

/**
 * Situation layers, bottom to top: road closures, drone plans and trails, areas, critical points, people.
 * Road colours follow the phone app (mobile/src/map/floodStyle.ts): red closed, amber likely, grey unchecked.
 * - Shapes say what a thing is: critical points are diamonds, people are filled dots (clustered with a
 *   count when zoomed out), areas are rings.
 * - Colour says how bad it is, with four colours only (--sev-critical, --sev-warning, --sev-muted, --drone).
 * - To keep the overview calm, watched points and at-risk areas appear only when zoomed in. Flooded
 *   points, cut-off areas and every drone target always show.
 */

type FC = GeoJSON.FeatureCollection
export type RegionPick = { kind: 'person'; id: string } | { kind: 'area'; id: string } | { kind: 'point'; id: string }

/** Detail that only appears once zoomed in past this. */
const DETAIL_ZOOM = 11.5
const DIAMOND = 'rg-diamond'
const PIN = 'rg-pin'
const PIN_DOT = 'rg-pin-dot'
const BADGE = 'rg-badge'

export const REGION_CLICKABLE = ['rg-people', 'rg-areas', 'rg-areas-risk', 'rg-points', 'rg-points-watch'] as const
export const REGION_ROADS = ['rg-roads-closed', 'rg-roads-likely', 'rg-roads-unknown'] as const
export const REGION_CLUSTER = 'rg-people-cluster'
const SOURCES = ['rg-roads', 'rg-paths', 'rg-trails', 'rg-scan', 'rg-areas', 'rg-points', 'rg-targets'] as const

function toneColor(read: (n: string) => string) {
  return ['match', ['get', 'tone'], 'critical', read('--sev-critical'), 'warning', read('--sev-warning'), read('--sev-muted')] as unknown as string
}

/** A white diamond drawn once as an SDF icon, so each point can be tinted by its tone. */
function addDiamond(map: MlMap): void {
  if (map.hasImage(DIAMOND)) return
  const size = 32
  const c = document.createElement('canvas')
  c.width = c.height = size
  const g = c.getContext('2d')
  if (!g) return
  g.fillStyle = '#fff'
  g.beginPath()
  g.moveTo(size / 2, 3)
  g.lineTo(size - 3, size / 2)
  g.lineTo(size / 2, size - 3)
  g.lineTo(3, size / 2)
  g.closePath()
  g.fill()
  map.addImage(DIAMOND, g.getImageData(0, 0, size, size), { sdf: true, pixelRatio: 2 })
}

/** Draws a white shape once as an SDF icon so layers can tint it. */
function addShape(map: MlMap, name: string, w: number, h: number, draw: (g: CanvasRenderingContext2D) => void): void {
  if (map.hasImage(name)) return
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const g = c.getContext('2d')
  if (!g) return
  g.fillStyle = '#fff'
  draw(g)
  map.addImage(name, g.getImageData(0, 0, w, h), { sdf: true, pixelRatio: 2 })
}

/** A map pin (the phone app's destination-pin shape): round head, point at the bottom. */
function addPinShapes(map: MlMap): void {
  addShape(map, PIN, 40, 52, (g) => {
    g.beginPath()
    g.arc(20, 18, 15, Math.PI * 0.8, Math.PI * 2.2)
    g.lineTo(20, 49)
    g.closePath()
    g.fill()
  })
  addShape(map, PIN_DOT, 40, 52, (g) => {
    g.beginPath()
    g.arc(20, 18, 6, 0, Math.PI * 2)
    g.fill()
  })
  addShape(map, BADGE, 48, 48, (g) => {
    g.beginPath()
    g.roundRect(4, 4, 40, 40, 10)
    g.fill()
  })
}

export function addRegionLayers(map: MlMap, read: (n: string) => string): void {
  if (map.getSource('rg-points')) return
  for (const id of SOURCES) map.addSource(id, { type: 'geojson', data: EMPTY })
  // People cluster below street level so a crowded town reads as one counted badge.
  map.addSource('rg-people', { type: 'geojson', data: EMPTY, cluster: true, clusterRadius: 38, clusterMaxZoom: 13 })
  addDiamond(map)
  addPinShapes(map)
  const tone = toneColor(read)
  const halo = read('--map-halo')
  const drone = read('--drone')
  const sel = read('--d-strong')
  const ink = read('--d-strong')
  const hasGlyphs = Boolean(map.getStyle().glyphs)

  // Road closures, like the phone map: unchecked roads only when zoomed in.
  const round = { 'line-cap': 'round', 'line-join': 'round' } as const
  const byStatus = (s: string) => ['==', ['get', 'status'], s] as unknown as never
  map.addLayer({ id: 'rg-roads-casing', type: 'line', source: 'rg-roads', filter: ['!=', ['get', 'status'], 'unknown'], layout: round, paint: { 'line-color': halo, 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 3, 14, 7] } })
  map.addLayer({ id: 'rg-roads-unknown', type: 'line', source: 'rg-roads', minzoom: 12, filter: byStatus('unknown'), layout: round, paint: { 'line-color': read('--sev-muted'), 'line-opacity': 0.35, 'line-width': 1.5 } })
  map.addLayer({ id: 'rg-roads-likely', type: 'line', source: 'rg-roads', filter: byStatus('likely_flooded'), layout: round, paint: { 'line-color': read('--sev-warning'), 'line-opacity': 0.6, 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 1.5, 14, 3] } })
  map.addLayer({ id: 'rg-roads-closed', type: 'line', source: 'rg-roads', filter: byStatus('confirmed_flooded'), layout: round, paint: { 'line-color': read('--sev-critical'), 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 2.5, 14, 4.5] } })

  map.addLayer({ id: 'rg-trails', type: 'line', source: 'rg-trails', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': drone, 'line-width': 2, 'line-opacity': 0.35 } })
  map.addLayer({ id: 'rg-paths', type: 'line', source: 'rg-paths', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': drone, 'line-width': 1.5, 'line-opacity': 0.6, 'line-dasharray': [2, 2] } })
  // A drone taking a look: its camera footprint (~300 m) as a soft disc. Grows with zoom so it stays in metres.
  map.addLayer({
    id: 'rg-scan', type: 'circle', source: 'rg-scan',
    paint: {
      'circle-radius': ['interpolate', ['exponential', 2], ['zoom'], 10, 2.5, 16, 160],
      'circle-color': drone,
      'circle-opacity': 0.12,
      'circle-stroke-color': drone,
      'circle-stroke-width': 1,
      'circle-stroke-opacity': 0.5,
    },
  })

  // Areas: rings. Cut off always; at risk only when zoomed in.
  const ring = {
    'circle-radius': ['interpolate', ['linear'], ['sqrt', ['get', 'households']], 1, 7, 5, 10, 15, 15],
    'circle-color': tone,
    'circle-opacity': 0.08,
    'circle-stroke-color': ['case', ['get', 'selected'], sel, tone],
    'circle-stroke-width': ['case', ['get', 'selected'], 2.5, 1.75],
  } as const
  map.addLayer({ id: 'rg-areas', type: 'circle', source: 'rg-areas', filter: ['==', ['get', 'tone'], 'critical'], paint: ring as never })
  map.addLayer({ id: 'rg-areas-risk', type: 'circle', source: 'rg-areas', minzoom: DETAIL_ZOOM, filter: ['!=', ['get', 'tone'], 'critical'], paint: ring as never })

  // Critical points: diamonds. Watched (grey, not a drone target) only when zoomed in.
  const diamond = (sizeFlag: number) => ({
    'icon-image': DIAMOND,
    'icon-size': ['case', ['get', 'selected'], 0.95, sizeFlag] as unknown as number,
    'icon-allow-overlap': true,
    'icon-ignore-placement': true,
  })
  const diamondPaint = { 'icon-color': ['case', ['get', 'selected'], sel, tone] as unknown as string, 'icon-halo-color': halo, 'icon-halo-width': 1.5 }
  map.addLayer({ id: 'rg-points-watch', type: 'symbol', source: 'rg-points', minzoom: DETAIL_ZOOM, filter: ['all', ['==', ['get', 'tone'], 'muted'], ['!', ['get', 'ranked']]], layout: diamond(0.5), paint: diamondPaint })
  map.addLayer({ id: 'rg-points', type: 'symbol', source: 'rg-points', filter: ['any', ['!=', ['get', 'tone'], 'muted'], ['get', 'ranked']], layout: { ...diamond(0.7), 'symbol-sort-key': ['get', 'rank'] as unknown as number }, paint: diamondPaint })

  map.addLayer({ id: 'rg-targets', type: 'circle', source: 'rg-targets', paint: { 'circle-radius': 11, 'circle-color': 'transparent', 'circle-stroke-color': drone, 'circle-stroke-width': 2 } })

  // People (Driver cases only): pins, so they never read as a point (diamond) or an area (ring).
  // Clusters are ink rounded squares with a count.
  map.addLayer({
    id: REGION_CLUSTER, type: 'symbol', source: 'rg-people', filter: ['has', 'point_count'],
    layout: {
      'icon-image': BADGE,
      'icon-size': ['step', ['get', 'point_count'], 0.95, 10, 1.1, 50, 1.25] as unknown as number,
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
      ...(hasGlyphs ? { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Open Sans Bold'], 'text-size': 12, 'text-allow-overlap': true, 'text-ignore-placement': true } : {}),
    } as never,
    paint: { 'icon-color': ink, 'icon-halo-color': halo, 'icon-halo-width': 2, 'text-color': halo } as never,
  })
  const pinSize = ['case', ['get', 'selected'], 1.05, ['get', 'stopped'], 0.95, 0.8] as unknown as number
  const pinLayout = { 'icon-size': pinSize, 'icon-anchor': 'bottom', 'icon-allow-overlap': true, 'icon-ignore-placement': true } as const
  map.addLayer({
    id: 'rg-people', type: 'symbol', source: 'rg-people', filter: ['!', ['has', 'point_count']],
    layout: { ...pinLayout, 'icon-image': PIN },
    paint: { 'icon-color': ['case', ['get', 'selected'], sel, tone] as unknown as string, 'icon-halo-color': halo, 'icon-halo-width': 1.5 },
  })
  map.addLayer({
    id: 'rg-people-dot', type: 'symbol', source: 'rg-people', filter: ['!', ['has', 'point_count']],
    layout: { ...pinLayout, 'icon-image': PIN_DOT },
    paint: { 'icon-color': halo },
  })
}

export interface RegionLayerData {
  info: RegionInfo | null
  points: readonly MapPoint[]
  roads: readonly FloodRoad[]
  /** Ids of the ranked points (the drones' work list): always drawn, ordered by rank. */
  ranked: readonly string[]
  areas: readonly Area[]
  people: readonly Person[]
  drones: readonly FleetDrone[]
  trails: Readonly<Record<string, [number, number][]>>
  pick: RegionPick | null
}

const pt = (lon: number, lat: number, props: Record<string, unknown>): GeoJSON.Feature => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] }, properties: props })
const isSel = (pick: RegionPick | null, kind: RegionPick['kind'], id: string) => pick?.kind === kind && pick.id === id

function set(map: MlMap, id: string, data: FC) {
  ;(map.getSource(id) as GeoJSONSource | undefined)?.setData(data)
}

function fc(features: GeoJSON.Feature[]): FC {
  return { type: 'FeatureCollection', features }
}

export function updateRegionLayers(map: MlMap, d: RegionLayerData): void {
  if (!map.getSource('rg-points')) return
  const line = (coords: [number, number][], id: string): GeoJSON.Feature => ({ type: 'Feature', geometry: { type: 'LineString', coordinates: coords }, properties: { id } })
  set(map, 'rg-roads', fc(d.roads.map((r) => ({ type: 'Feature', geometry: { type: 'LineString', coordinates: r.coords }, properties: { id: r.id, status: r.status, name: r.name } }))))
  set(map, 'rg-paths', fc(d.drones.filter((x) => x.status !== 'idle' && x.path.length > 1).map((x) => line(x.path, x.id))))
  set(map, 'rg-trails', fc(Object.entries(d.trails).filter(([, t]) => t.length > 1).map(([id, t]) => line(t, id))))
  set(map, 'rg-scan', fc(d.drones.filter((x) => x.status === 'snapshot').map((x) => pt(x.lon, x.lat, { id: x.id }))))
  const where = new Map(d.points.map((p) => [p.id, p]))
  set(map, 'rg-targets', fc(d.drones.filter((x) => x.status === 'flying' && x.target && where.has(x.target)).map((x) => {
    const p = where.get(x.target as string) as MapPoint
    return pt(p.lon, p.lat, { id: x.id })
  })))
  set(map, 'rg-areas', fc(d.areas.map((a) => pt(a.lon, a.lat, { id: a.id, households: a.households, tone: areaTone(a.status), selected: isSel(d.pick, 'area', a.id) }))))
  // Higher sort key draws on top: flooded over likely over watched, and ranked points by priority.
  const sev = (t: Tone) => (t === 'muted' ? 0 : t === 'warning' ? 100 : 200)
  const rankOf = new Map(d.ranked.map((id, i) => [id, i]))
  set(map, 'rg-points', fc(d.points.map((p) => {
    const tone = pointTone(p.status)
    const r = rankOf.get(p.id)
    return pt(p.lon, p.lat, { id: p.id, tone, ranked: r !== undefined, rank: sev(tone) + (r === undefined ? 0 : 50 - r), selected: isSel(d.pick, 'point', p.id) })
  })))
  set(map, 'rg-people', fc(d.people.filter((p) => p.location.lon != null && p.location.lat != null).map((p) => pt(p.location.lon as number, p.location.lat as number, { id: p.user_id, tone: personTone(p.level), stopped: p.stopped_in_water, selected: isSel(d.pick, 'person', p.user_id) }))))
}
