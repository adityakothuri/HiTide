import type { GeoJSONSource, ImageSource, Map as MlMap, RasterTileSource } from 'maplibre-gl'
import type { Town } from '../data/types'
import type { WxLayers } from '../wx/useWx'
import type { RainProduct, WxSnapshot, WxSource } from '../wx/types'
import { EMPTY } from './mapData'

/**
 * Hydromet layers for the ops console, bottom to top: rain (MRMS raster), modelled flood depth (image),
 * likely-flooded and closed roads, gauges. No glow: the data carries the color.
 */

const RAIN_OPACITY = 0.6
const DEPTH_OPACITY = 0.7
const PRODUCTS: RainProduct[] = ['p1h', 'p24h']
const BLANK_PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='

export const WX_CLICKABLE = ['wx-gauges', 'wx-roads-closed', 'wx-roads-likely'] as const

const rainId = (p: RainProduct) => `wx-rain-${p}`

const RAIN_SMOOTH_MAXZOOM = 8

export function addWxLayers(map: MlMap, source: WxSource, read: (n: string) => string, beforeId?: string): void {
  for (const p of PRODUCTS) {
    map.addSource(rainId(p), {
      type: 'raster',
      tiles: [source.at(source.range[0]).rainTiles(p) ?? ''],
      tileSize: 256,
      minzoom: source.rain.minzoom,
      // Overzoom the coarsest cached tiles (~600 m pixels at z8) so linear resampling smooths the ~1 km MRMS
      // grid into a continuous field, the way radar viewers draw it, instead of hard 1 km blocks.
      maxzoom: Math.min(source.rain.maxzoom, RAIN_SMOOTH_MAXZOOM),
      bounds: source.rain.bounds,
    })
    map.addLayer({ id: rainId(p), type: 'raster', source: rainId(p), layout: { visibility: 'none' }, paint: { 'raster-opacity': RAIN_OPACITY, 'raster-fade-duration': 0, 'raster-resampling': 'linear' } }, beforeId)
  }

  map.addSource('wx-depth', { type: 'image', url: BLANK_PNG, coordinates: [[0, 0.0001], [0.0001, 0.0001], [0.0001, 0], [0, 0]] })
  map.addLayer({ id: 'wx-depth', type: 'raster', source: 'wx-depth', paint: { 'raster-opacity': DEPTH_OPACITY, 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } }, beforeId)

  map.addSource('wx-roads', { type: 'geojson', data: EMPTY })
  // Roads sit on the map instead of fighting it: zoom-scaled width, a thin halo casing, round ends,
  // and likely-flooded roads only once they're legible (z11+).
  const width = ['interpolate', ['linear'], ['zoom'], 9, 1, 12, 2, 15, 3.5] as unknown as number
  const casing = ['interpolate', ['linear'], ['zoom'], 9, 2.5, 12, 4, 15, 6.5] as unknown as number
  const round = { 'line-cap': 'round', 'line-join': 'round' } as const
  map.addLayer({ id: 'wx-roads-casing', type: 'line', source: 'wx-roads', layout: round, paint: { 'line-color': read('--map-halo'), 'line-width': casing, 'line-opacity': 0.85 } }, beforeId)
  map.addLayer({ id: 'wx-roads-likely', type: 'line', source: 'wx-roads', minzoom: 11, filter: ['==', ['get', 'status'], 'likely'], layout: round, paint: { 'line-color': read('--wx-road-likely'), 'line-width': width, 'line-dasharray': [0.6, 1.8], 'line-opacity': 0.9 } }, beforeId)
  map.addLayer({ id: 'wx-roads-closed', type: 'line', source: 'wx-roads', filter: ['==', ['get', 'status'], 'closed'], layout: round, paint: { 'line-color': read('--wx-road-closed'), 'line-width': width, 'line-opacity': 0.9 } }, beforeId)

  const cat = ['match', ['get', 'category'],
    'major', read('--wx-cat-major'), 'moderate', read('--wx-cat-moderate'), 'minor', read('--wx-cat-minor'),
    'action', read('--wx-cat-action'), 'below', read('--wx-cat-below'), read('--wx-cat-none')] as unknown as string
  map.addSource('wx-gauges', { type: 'geojson', data: EMPTY })
  // Gauges sit above everything, labels included, like station dots on NWS maps.
  map.addLayer({
    id: 'wx-gauges', type: 'circle', source: 'wx-gauges',
    paint: {
      'circle-radius': ['case', ['get', 'selected'], 7, 5],
      'circle-color': cat,
      // 10 px dots with a thin white stroke, like NWS station maps; a dark ring marks the selection.
      'circle-stroke-color': ['case', ['get', 'selected'], read('--d-strong'), read('--map-halo')],
      'circle-stroke-width': ['case', ['get', 'selected'], 2.5, 1.5],
    },
  })
}

/** Deduplicated road lines (a two-way street is two directed edges with one geometry). */
function roadsFc(town: Town, snap: WxSnapshot, selectedRoad: string | null): GeoJSON.FeatureCollection {
  const seen = new Set<string>()
  const features: GeoJSON.Feature[] = []
  for (const f of town.segments.features) {
    const id = f.properties.edge_id
    const status = snap.roads.closed.has(id) ? 'closed' : snap.roads.likely.has(id) ? 'likely' : null
    if (!status) continue
    const [u, v] = id.split('-')
    const key = u < v ? `${u}-${v}` : `${v}-${u}`
    if (seen.has(key)) continue
    seen.add(key)
    features.push({ type: 'Feature', geometry: f.geometry, properties: { id, status, name: f.properties.name, selected: id === selectedRoad } })
  }
  return { type: 'FeatureCollection', features }
}

function gaugesFc(snap: WxSnapshot, selectedGauge: string | null): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: snap.gauges.map((g) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [g.lon, g.lat] },
      properties: {
        site: g.site,
        category: g.stageFt == null ? 'none' : g.category,
        selected: g.site === selectedGauge,
      },
    })),
  }
}

export interface WxSelection { gauge: string | null; road: string | null }

/** Pushes the snapshot at time t into the map. Cheap enough to call on every slider step. */
export function updateWxLayers(map: MlMap, town: Town, snap: WxSnapshot, layers: WxLayers, sel: WxSelection): void {
  for (const p of PRODUCTS) {
    const on = layers.base === 'rain' && layers.rainProduct === p && snap.rainTiles(p) != null
    map.setLayoutProperty(rainId(p), 'visibility', on ? 'visible' : 'none')
    map.setPaintProperty(rainId(p), 'raster-opacity', layers.opacity)
    const src = map.getSource(rainId(p)) as RasterTileSource | undefined
    const url = snap.rainTiles(p)
    if (on && url && src && src.tiles?.[0] !== url) src.setTiles([url])
  }

  const depthOn = layers.base === 'depth' && snap.depth != null
  map.setLayoutProperty('wx-depth', 'visibility', depthOn ? 'visible' : 'none')
  map.setPaintProperty('wx-depth', 'raster-opacity', Math.min(1, layers.opacity + 0.15))
  if (depthOn && snap.depth) {
    const img = map.getSource('wx-depth') as ImageSource | undefined
    if (img && img.url !== snap.depth.url) img.updateImage({ url: snap.depth.url, coordinates: snap.depth.coordinates })
  }

  const roadsVis = layers.roads ? 'visible' : 'none'
  map.setLayoutProperty('wx-roads-likely', 'visibility', roadsVis)
  if (map.getLayer('wx-roads-casing')) map.setLayoutProperty('wx-roads-casing', 'visibility', roadsVis)
  map.setLayoutProperty('wx-roads-closed', 'visibility', roadsVis)
  ;(map.getSource('wx-roads') as GeoJSONSource | undefined)?.setData(layers.roads ? roadsFc(town, snap, sel.road) : EMPTY)

  map.setLayoutProperty('wx-gauges', 'visibility', layers.gauges ? 'visible' : 'none')
  ;(map.getSource('wx-gauges') as GeoJSONSource | undefined)?.setData(gaugesFc(snap, sel.gauge))
}
