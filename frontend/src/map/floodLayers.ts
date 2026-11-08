import type { GeoJSONSource, Map as MlMap } from 'maplibre-gl'
import type { Town } from '../data/types'
import { EMPTY } from './mapData'
import type { MapMode, MapTheme } from './basemap'

export const DYNAMIC_SOURCES = ['flooded', 'hazards', 'reroutes', 'drivers', 'cases', 'trails', 'focus'] as const
export type DynamicSource = (typeof DYNAMIC_SOURCES)[number]

interface Opts {
  theme: MapTheme
  mode: MapMode
  read: (name: string) => string
  beforeId?: string
}

/** Flood overlays shared by the console map and the phone's mini maps. Safe to call after every style load. */
export function addFloodLayers(map: MlMap, town: Town, { theme, mode, read, beforeId }: Opts): void {
  const w = (n: number) => read(`--water-${n}`)
  const dark = theme === 'dark'
  const halo = dark ? read('--d-bg') : read('--surface')

  // Offline only: draw the town ourselves.
  if (mode === 'offline') {
    map.addSource('river', { type: 'geojson', data: town.river as GeoJSON.GeoJSON })
    map.addSource('roads', { type: 'geojson', data: town.segments })
    map.addLayer({ id: 'river-wide', type: 'line', source: 'river', paint: { 'line-color': dark ? read('--d-raised') : w(1), 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 6, 16, 28] } })
    map.addLayer({ id: 'roads', type: 'line', source: 'roads', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': dark ? read('--d-hover') : read('--neutral-3'), 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 0.6, 16, 2.5] } })
  }

  for (const id of DYNAMIC_SOURCES) map.addSource(id, { type: 'geojson', data: EMPTY })

  const statusColor = ['match', ['get', 'status'], 'caution', w(2), 'closed', w(3), 'float', w(4), w(5)] as unknown as string
  const width = (k: number) =>
    ['interpolate', ['linear'], ['zoom'], 12, ['*', k, ['match', ['get', 'status'], 'caution', 1.2, 2.2]], 16, ['*', k, ['match', ['get', 'status'], 'caution', 3.5, 6]]] as unknown as number

  // Soft glow under flooded roads on the dark map; a white casing on the light one.
  map.addLayer({ id: 'flooded-glow', type: 'line', source: 'flooded', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': halo, 'line-width': width(1.8), 'line-opacity': dark ? 0.8 : 1 } }, beforeId)
  map.addLayer({ id: 'flooded', type: 'line', source: 'flooded', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': statusColor, 'line-width': width(1) } }, beforeId)
  map.addLayer({ id: 'reroutes-casing', type: 'line', source: 'reroutes', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': halo, 'line-width': 7 } })
  map.addLayer({ id: 'reroutes', type: 'line', source: 'reroutes', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': read('--safe'), 'line-width': dark ? 3 : 4, 'line-opacity': dark ? 0.85 : 1 } })
  map.addLayer({ id: 'hazards', type: 'line', source: 'hazards', layout: { 'line-cap': 'round' }, paint: { 'line-color': read('--critical'), 'line-width': 3, 'line-dasharray': [2, 1.5] } })
  map.addLayer({ id: 'trails', type: 'line', source: 'trails', paint: { 'line-color': read('--info'), 'line-width': 2, 'line-dasharray': [1, 1.5] } })
  map.addLayer({
    id: 'drivers', type: 'circle', source: 'drivers',
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 2.5, 16, 5],
      'circle-color': dark ? read('--d-muted') : read('--neutral-5'),
      'circle-opacity': 0.6,
      'circle-stroke-color': halo, 'circle-stroke-width': 1,
    },
  })
  const sev = ['match', ['get', 'severity'], 'critical', read('--critical'), 'caution', read('--caution-mark'), read('--safe')] as unknown as string
  map.addLayer({ id: 'case-pulse', type: 'circle', source: 'cases', paint: { 'circle-radius': 18, 'circle-color': sev, 'circle-opacity': 0.1 } })
  map.addLayer({ id: 'case-halo', type: 'circle', source: 'cases', paint: { 'circle-radius': ['case', ['get', 'selected'], 15, 12], 'circle-color': 'transparent', 'circle-stroke-width': 2, 'circle-stroke-color': sev } })
  map.addLayer({ id: 'case-dot', type: 'circle', source: 'cases', paint: { 'circle-radius': 7, 'circle-color': sev, 'circle-stroke-color': halo, 'circle-stroke-width': 2 } })
  // Phone: "you are here" style point.
  map.addLayer({ id: 'focus-halo', type: 'circle', source: 'focus', paint: { 'circle-radius': 14, 'circle-color': read('--ios-blue') || read('--info'), 'circle-opacity': 0.18 } })
  map.addLayer({ id: 'focus', type: 'circle', source: 'focus', paint: { 'circle-radius': 6, 'circle-color': read('--ios-blue') || read('--info'), 'circle-stroke-color': read('--on-dark'), 'circle-stroke-width': 2 } })
}

export function setSource(map: MlMap, id: DynamicSource, data: GeoJSON.GeoJSON): void {
  ;(map.getSource(id) as GeoJSONSource | undefined)?.setData(data)
}
