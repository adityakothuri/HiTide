import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource, Map as MlMap } from 'maplibre-gl'
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Crosshair } from 'lucide-react'
import { Colorbar } from '../../console/Colorbar'
import { MapView, type Feature } from '../../console/MapView'
import { tokenReader } from '../../map/basemap'
import { useWx } from '../../wx/useWx'
import type { Road } from '../types'
import { midpoint } from './derive'
import s from './EvidenceMap.module.css'

interface Props {
  roads: Road[]
  selectedId: string
  onSelect: (id: string) => void
  /** Pixels on the right covered by a floating panel; the map centre and controls stay clear of it. */
  inset?: number
}

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }
const FIT_PADDING = 40
const MAX_FIT_ZOOM = 15.5
const MAX_CALLOUTS = 4
/** Screen distance (px) around the selected label kept free of other callouts. */
const CALLOUT_CLEAR_X = 180
const CALLOUT_CLEAR_Y = 48
const MAP_PADDING = { left: 16, right: 16, bottom: 16 }
const LAYERS = ['ev-halo', 'ev-open', 'ev-unknown', 'ev-closed', 'ev-hit'] as const

function toFc(roads: Road[], selectedId: string): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: roads
      .filter((r) => r.geometry?.coordinates?.length)
      .map((r) => ({ type: 'Feature', geometry: r.geometry, properties: { id: r.id, access: r.access, selected: r.id === selectedId } })),
  }
}

function boundsOf(roads: Road[]): maplibregl.LngLatBounds | null {
  const pts = roads.flatMap((r) => r.geometry?.coordinates ?? [])
  if (!pts.length) return null
  const b = new maplibregl.LngLatBounds(pts[0] as [number, number], pts[0] as [number, number])
  for (const p of pts) b.extend(p as [number, number])
  return b
}

/** Inspection overlay on top of the shared hydromet map: evidence roads above rain, depth and gauges. */
function addOverlay(map: MlMap, read: (n: string) => string) {
  if (map.getSource('ev-roads')) return
  map.addSource('ev-roads', { type: 'geojson', data: EMPTY })
  map.addLayer({ id: 'ev-halo', type: 'line', source: 'ev-roads', filter: ['==', ['get', 'selected'], true],
    layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': read('--ops-amber'), 'line-width': 16, 'line-opacity': 0.28 } })
  map.addLayer({ id: 'ev-open', type: 'line', source: 'ev-roads', filter: ['==', ['get', 'access'], 'open'],
    layout: { 'line-cap': 'round' }, paint: { 'line-color': read('--ops-open-on-dark'), 'line-width': 4 } })
  map.addLayer({ id: 'ev-unknown', type: 'line', source: 'ev-roads', filter: ['in', ['get', 'access'], ['literal', ['unknown', 'restricted']]],
    paint: { 'line-color': read('--ops-amber'), 'line-width': 4.5, 'line-dasharray': [2, 1.4] } })
  map.addLayer({ id: 'ev-closed', type: 'line', source: 'ev-roads', filter: ['==', ['get', 'access'], 'closed'],
    paint: { 'line-color': read('--ops-closed'), 'line-width': 5.5 } })
  map.addLayer({ id: 'ev-hit', type: 'line', source: 'ev-roads', paint: { 'line-color': '#000', 'line-opacity': 0, 'line-width': 18 } })
}

export function EvidenceMap({ roads, selectedId, onSelect, inset = 0 }: Props) {
  // Road verification reads best without a base field; gauges and closures stay as overlays.
  const wx = useWx('none')
  const wrapRef = useRef<HTMLDivElement>(null)
  const [feature, setFeature] = useState<Feature | null>(null)
  const [{ map, version }, setMapState] = useState<{ map: MlMap | null; version: number }>({ map: null, version: 0 })
  const markers = useRef<maplibregl.Marker[]>([])
  const onSelectRef = useRef(onSelect)
  // Map padding stays small; framing adds the inset so roads land in the visible part of the map.
  const fitPadding = useMemo(() => ({ top: FIT_PADDING, bottom: FIT_PADDING, left: FIT_PADDING, right: FIT_PADDING + inset }), [inset])
  // The shared map chrome positions itself from these console offsets.
  const chromeVars = useMemo(() => ({ '--left-w': '0px', '--detail-w': `${inset}px` }) as CSSProperties, [inset])
  const bounds = useMemo(() => boundsOf(roads), [roads])
  const boundsKey = bounds ? bounds.toArray().flat().map((n) => n.toFixed(4)).join(',') : ''

  useEffect(() => { onSelectRef.current = onSelect }, [onSelect])
  const onMap = useCallback((m: MlMap | null, v: number) => setMapState({ map: m, version: v }), [])

  // Add the overlay each time the style is rebuilt, and handle clicks on evidence roads.
  useEffect(() => {
    if (!map || !version || !wrapRef.current) return
    addOverlay(map, tokenReader(wrapRef.current))
    const click = (e: maplibregl.MapLayerMouseEvent) => {
      const id = e.features?.[0]?.properties?.id
      if (typeof id === 'string') onSelectRef.current(id)
    }
    const enter = () => { map.getCanvas().style.cursor = 'pointer' }
    const leave = () => { map.getCanvas().style.cursor = '' }
    map.on('click', 'ev-hit', click)
    map.on('mouseenter', 'ev-hit', enter)
    map.on('mouseleave', 'ev-hit', leave)
    return () => {
      map.off('click', 'ev-hit', click)
      map.off('mouseenter', 'ev-hit', enter)
      map.off('mouseleave', 'ev-hit', leave)
    }
  }, [map, version])

  // Weather layers load asynchronously; keep evidence drawn above them.
  useEffect(() => {
    if (!map || !version) return
    for (const id of LAYERS) if (map.getLayer(id)) map.moveLayer(id)
  }, [map, version, wx.snapshot, wx.layers])

  // Frame the evidence when the set of roads changes (before callouts, which are placed from the framed view).
  useEffect(() => {
    if (!map || !version || !bounds) return
    map.fitBounds(bounds, { padding: fitPadding, maxZoom: MAX_FIT_ZOOM, animate: false })
  }, [map, version, boundsKey, fitPadding]) // eslint-disable-line react-hooks/exhaustive-deps

  // Road data and callouts.
  useEffect(() => {
    if (!map || !version) return
    ;(map.getSource('ev-roads') as GeoJSONSource | undefined)?.setData(toFc(roads, selectedId))
    markers.current.forEach((m) => m.remove())
    const next: maplibregl.Marker[] = []
    const add = (el: HTMLElement, at: [number, number], anchor: maplibregl.PositionAnchor) =>
      next.push(new maplibregl.Marker({ element: el, anchor }).setLngLat(at).addTo(map))
    for (const r of roads.filter((x) => x.agreement === 'conflicting')) {
      const at = midpoint(r)
      if (!at) continue
      const el = document.createElement('button')
      el.type = 'button'
      el.className = s.diamond
      el.setAttribute('aria-label', `${r.name}: conflicting reports`)
      el.addEventListener('click', () => onSelectRef.current(r.id))
      add(el, at, 'center')
    }
    const selected = roads.find((r) => r.id === selectedId)
    const at = selected ? midpoint(selected) : null
    // Skip closure callouts that would sit on top of the selected road's label.
    const pinned = at ? map.project(at) : null
    const crowds = (p: [number, number]) => {
      if (!pinned) return false
      const q = map.project(p)
      return Math.abs(q.x - pinned.x) < CALLOUT_CLEAR_X && Math.abs(q.y - pinned.y) < CALLOUT_CLEAR_Y
    }
    for (const r of roads.filter((x) => x.access === 'closed' && x.id !== selectedId).slice(0, MAX_CALLOUTS)) {
      const at = midpoint(r)
      if (!at || crowds(at)) continue
      const el = document.createElement('div')
      el.className = `${s.callout} ${s.calloutClosed}`
      el.textContent = 'Closure reported'
      add(el, at, 'bottom')
    }
    if (selected && at) {
      const el = document.createElement('div')
      el.className = s.selectedMarker
      const label = document.createElement('span')
      label.className = `${s.callout} ${s.calloutSelected}`
      label.textContent = selected.name || selected.id
      const pin = document.createElement('span')
      pin.className = s.pin
      el.append(label, pin)
      add(el, at, 'bottom')
    }
    markers.current = next
    return () => next.forEach((m) => m.remove())
  }, [map, version, roads, selectedId])

  const recenter = () => {
    if (map && bounds) map.fitBounds(bounds, { padding: fitPadding, maxZoom: MAX_FIT_ZOOM })
  }

  return (
    <div ref={wrapRef} className={s.wrap} data-theme="dispatch" style={chromeVars} role="region" aria-label="Flood map with road evidence. The inspection queue lists the same roads.">
      <MapView padding={MAP_PADDING} wx={wx} feature={feature} onFeature={setFeature} onMap={onMap} />
      <Colorbar wx={wx} />
      <button type="button" className={s.fit} onClick={recenter} aria-label="Fit map to road evidence" disabled={!bounds}>
        <Crosshair size={16} />
      </button>
      <dl className={s.legend} aria-label="Road evidence legend">
        <div><dt><i className={s.lgClosed} /></dt><dd>Closed (reported)</dd></div>
        <div><dt><i className={s.lgUnknown} /></dt><dd>Needs verification</dd></div>
        <div><dt><i className={s.lgDiamond} /></dt><dd>Conflicting</dd></div>
        <div><dt><i className={s.lgOpen} /></dt><dd>Reported open</dd></div>
      </dl>
    </div>
  )
}
