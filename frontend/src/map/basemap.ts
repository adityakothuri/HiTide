import * as maplibregl from 'maplibre-gl'
// Vite bundles maplibre's worker so it loads offline and survives dep pre-bundling.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { Map as MlMap, StyleSpecification } from 'maplibre-gl'

maplibregl.setWorkerUrl(workerUrl)

export type MapTheme = 'dark' | 'light'
export type MapMode = 'tiles' | 'offline'

// Keyless CARTO vector basemaps (OpenStreetMap data). Override with VITE_BASEMAP_DARK / VITE_BASEMAP_LIGHT.
const STYLE_URL: Record<MapTheme, string> = {
  dark: (import.meta.env.VITE_BASEMAP_DARK as string | undefined) ?? 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
  light: (import.meta.env.VITE_BASEMAP_LIGHT as string | undefined) ?? 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
}

export const BASEMAP_TIMEOUT_MS = 4000
export const ATTRIBUTION = '© OpenStreetMap contributors, © CARTO'

/** Reads a token from the element's scope, so themed containers get their own colors. */
export function tokenReader(el: Element): (name: string) => string {
  const cs = getComputedStyle(el)
  return (name) => cs.getPropertyValue(name).trim()
}

export function styleUrl(theme: MapTheme): string {
  return STYLE_URL[theme]
}

/** Offline stand-in: plain background. Roads and river come from the bundled town data. */
export function localStyle(bg: string): StyleSpecification {
  return { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': bg } }] }
}

const HIDE = [/^poi_/, /^housenumber$/, /^aeroway/, /^boundary_/, /^place_(country|state|continent|capital)/, /^watername_(ocean|sea)/]

/** Quiet the basemap so our flood data reads first: no POIs or house numbers, tinted water. */
export function tuneBasemap(map: MlMap, theme: MapTheme, read: (n: string) => string): void {
  for (const layer of map.getStyle().layers ?? []) {
    if (HIDE.some((re) => re.test(layer.id))) map.setLayoutProperty(layer.id, 'visibility', 'none')
  }
  const water = theme === 'dark' ? read('--d-raised') : read('--water-1')
  if (map.getLayer('water')) map.setPaintProperty('water', 'fill-color', water)
  if (map.getLayer('background') && theme === 'dark') map.setPaintProperty('background', 'background-color', read('--d-bg'))
}

/** First label layer, so flood lines draw above roads but under street names. */
export function firstLabelLayer(map: MlMap): string | undefined {
  // Street names come last in CARTO styles; water labels sit before the roads in some styles.
  const layers = map.getStyle().layers ?? []
  return (layers.find((l) => l.id.startsWith('roadname_')) ?? layers.find((l) => l.id.startsWith('place_')))?.id
}

export function reducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
