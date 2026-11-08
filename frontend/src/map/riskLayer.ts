import type { GeoJSONSource, ImageSource, Map as MlMap } from 'maplibre-gl'
import type { RiskIndex } from '../risk/grid'
import { paintGrid } from '../risk/paint'
import { EMPTY } from './mapData'

/**
 * Flood risk surface: the Float32 grid painted with Turbo onto a canvas, shown as two image sources
 * that crossfade on frame change, under the basemap labels. A study-area outline and an outside mask
 * frame the extent like a clipped GIS map.
 */
const IDS = ['risk-a', 'risk-b'] as const
const UPSAMPLE = 2
const FADE_MS = 350
const BLANK_PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
const WORLD: GeoJSON.Position[] = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]]

type Quad = [[number, number], [number, number], [number, number], [number, number]]

function quad(idx: RiskIndex): Quad {
  const [w, s, e, n] = idx.bounds
  return [[w, n], [e, n], [e, s], [w, s]]
}

export function addRiskLayers(map: MlMap, read: (n: string) => string, beforeId?: string): void {
  if (map.getSource(IDS[0])) return
  for (const id of IDS) {
    map.addSource(id, { type: 'image', url: BLANK_PNG, coordinates: [[0, 0.0001], [0.0001, 0.0001], [0.0001, 0], [0, 0]] })
    map.addLayer({
      id, type: 'raster', source: id, layout: { visibility: 'none' },
      paint: { 'raster-opacity': 0, 'raster-opacity-transition': { duration: FADE_MS, delay: 0 }, 'raster-fade-duration': 0, 'raster-resampling': 'linear' },
    }, beforeId)
  }
  map.addSource('risk-area', { type: 'geojson', data: EMPTY })
  // The study area is the terrain grid's footprint, which sits slightly rotated on the web map, so it isn't
  // drawn as an outline or mask: the surface itself fades to nothing outside its data.
  void read
  views.set(map, { front: 0, shown: null })
}

/** Outline of the study area plus a mask over everything outside it. */
export function setStudyArea(map: MlMap, area: GeoJSON.Polygon | null): void {
  const src = map.getSource('risk-area') as GeoJSONSource | undefined
  if (!src) return
  if (!area) {
    src.setData(EMPTY)
    return
  }
  const ring = area.coordinates[0]
  src.setData({
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', properties: { role: 'mask' }, geometry: { type: 'Polygon', coordinates: [WORLD, [...ring].reverse()] } },
      { type: 'Feature', properties: { role: 'outline' }, geometry: { type: 'LineString', coordinates: ring } },
    ],
  })
}

function toDataUrl(values: Float32Array, idx: RiskIndex): string {
  const canvas = document.createElement('canvas')
  canvas.width = idx.width * UPSAMPLE
  canvas.height = idx.height * UPSAMPLE
  const ctx = canvas.getContext('2d')
  if (!ctx) return BLANK_PNG
  const px = paintGrid(values, idx.width, idx.height, UPSAMPLE)
  ctx.putImageData(new ImageData(px, canvas.width, canvas.height), 0, 0)
  return canvas.toDataURL('image/png')
}

const painted = new WeakMap<Float32Array, string>()

export interface RiskView {
  visible: boolean
  opacity: number
  idx: RiskIndex | null
  values: Float32Array | null
  frameId: string | null
  reducedMotion: boolean
}

/** Per map: which of the two sources is in front, and which frame it shows. Reset when sources are rebuilt. */
const views = new WeakMap<MlMap, { front: 0 | 1; shown: string | null }>()

/** Shows the frame; a new frame goes to the back source and fades in over the old one. */
export function updateRiskLayers(map: MlMap, v: RiskView): void {
  if (!map.getSource(IDS[0])) return
  const vis = v.visible && v.idx && v.values ? 'visible' : 'none'
  for (const id of IDS) map.setLayoutProperty(id, 'visibility', vis)
  for (const id of ['risk-mask', 'risk-outline']) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', v.visible ? 'visible' : 'none')
  if (vis === 'none' || !v.idx || !v.values) return
  const fade = v.reducedMotion ? 0 : FADE_MS
  for (const id of IDS) map.setPaintProperty(id, 'raster-opacity-transition', { duration: fade, delay: 0 })

  const view = views.get(map) ?? { front: 0, shown: null }
  if (view.shown !== v.frameId) {
    let dataUrl = painted.get(v.values)
    if (!dataUrl) {
      dataUrl = toDataUrl(v.values, v.idx)
      painted.set(v.values, dataUrl)
    }
    const back = view.front === 0 ? 1 : 0
    ;(map.getSource(IDS[back]) as ImageSource).updateImage({ url: dataUrl, coordinates: quad(v.idx) })
    view.front = back
    view.shown = v.frameId
    views.set(map, view)
  }
  map.setPaintProperty(IDS[view.front], 'raster-opacity', v.opacity)
  map.setPaintProperty(IDS[1 - view.front], 'raster-opacity', 0)
}
