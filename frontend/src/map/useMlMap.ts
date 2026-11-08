import * as maplibregl from 'maplibre-gl'
import type { Map as MlMap, MapOptions } from 'maplibre-gl'
import { useEffect, useRef, useState, type RefObject } from 'react'
import type { Town } from '../data/types'
import { BASEMAP_TIMEOUT_MS, firstLabelLayer, localStyle, styleUrl, tokenReader, tuneBasemap, type MapMode, type MapTheme } from './basemap'
import { addFloodLayers } from './floodLayers'

const TILE_ERRORS_BEFORE_FALLBACK = 6
const TILE_ERROR_WINDOW_MS = 10_000

export interface MlMapState {
  map: MlMap | null
  /** Increments each time layers are (re)built, so data effects re-push. 0 = not ready. */
  version: number
  mode: MapMode
}

/**
 * MapLibre map on a real basemap with our flood layers on top. Falls back to the bundled town
 * data if the basemap doesn't load in time or tiles keep failing (venue Wi-Fi).
 */
export function useMlMap(
  container: RefObject<HTMLDivElement | null>,
  town: Town | null,
  theme: MapTheme,
  options: Partial<MapOptions> = {},
): MlMapState {
  const [state, setState] = useState<MlMapState>({ map: null, version: 0, mode: 'tiles' })
  const optsRef = useRef(options)

  useEffect(() => {
    const el = container.current
    if (!el || !town) return
    const read = tokenReader(el)
    let mode: MapMode = navigator.onLine ? 'tiles' : 'offline'
    let tileErrors: number[] = []
    let version = 0

    const map = new maplibregl.Map({
      container: el,
      style: mode === 'tiles' ? styleUrl(theme) : localStyle(theme === 'dark' ? read('--d-bg') : read('--surface-page')),
      bounds: town.bounds,
      fitBoundsOptions: { padding: 32 },
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      ...optsRef.current,
    })
    map.touchZoomRotate.disableRotation()

    const build = () => {
      if (mode === 'tiles') tuneBasemap(map, theme, read)
      addFloodLayers(map, town, { theme, mode, read, beforeId: mode === 'tiles' ? firstLabelLayer(map) : undefined })
      version += 1
      setState({ map, version, mode })
    }
    const fallback = () => {
      if (mode === 'offline') return
      mode = 'offline'
      map.setStyle(localStyle(theme === 'dark' ? read('--d-bg') : read('--surface-page')), { diff: false })
    }

    map.on('style.load', build)
    // isStyleLoaded() is also false while tiles stream in, so only `version` (style.load fired) counts here.
    const timer = window.setTimeout(() => { if (version === 0) fallback() }, BASEMAP_TIMEOUT_MS)
    map.on('error', (e) => {
      if (mode === 'offline') return
      const isStyle = version === 0
      // Only a burst of failures (Wi-Fi gone) switches to offline; stray 404s over a long demo don't.
      const now = Date.now()
      tileErrors = [...tileErrors.filter((t) => now - t < TILE_ERROR_WINDOW_MS), now]
      if (isStyle || tileErrors.length >= TILE_ERRORS_BEFORE_FALLBACK) fallback()
      void e
    })

    return () => {
      window.clearTimeout(timer)
      setState({ map: null, version: 0, mode: 'tiles' })
      map.remove()
    }
  }, [container, town, theme])

  return state
}
