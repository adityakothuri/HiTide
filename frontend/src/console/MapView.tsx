import * as maplibregl from 'maplibre-gl'
import type { Map as MlMap, MapLayerMouseEvent } from 'maplibre-gl'
import { useEffect, useMemo, useRef } from 'react'
import type { Town } from '../data/types'
import { useTown } from '../hooks/useTown'
import { ATTRIBUTION, tokenReader } from '../map/basemap'
import { bearing, casesFc } from '../map/mapData'
import { setSource } from '../map/floodLayers'
import { useMlMap } from '../map/useMlMap'
import { addWxLayers, updateWxLayers, WX_CLICKABLE, type WxSelection } from '../map/wxLayers'
import { useApp, useStore, useUi } from '../state/StoreContext'
import { ErrorState, Loading } from '../ui/States'
import { CATEGORY_LABEL } from '../wx/category'
import type { WxState } from '../wx/useWx'
import s from './MapView.module.css'

const DRONE_ANIM_MS = 600
const FLY_ZOOM = 15
/** Hunt to Kerrville along the Guadalupe: every replay gauge and the town in view. */
const START_BOUNDS: [[number, number], [number, number]] = [[-99.36, 29.99], [-99.06, 30.105]]
/** Simulation layers the shared map adds that the console doesn't show; road status comes from the wx source. */
const HIDDEN_SIM_LAYERS = ['flooded-glow', 'flooded', 'case-pulse', 'case-halo', 'hazards', 'reroutes-casing', 'reroutes', 'trails', 'drivers', 'focus', 'focus-halo']

export interface Padding { left: number; right: number; bottom: number }
export type Feature = { kind: 'gauge'; site: string } | { kind: 'road'; edgeId: string }

function reducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

const DRONE_SVG =
  '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 3l6 16-6-4-6 4z" fill="currentColor" stroke="black" stroke-width="1" stroke-linejoin="round"/></svg>'

interface Props {
  padding: Padding
  wx: WxState
  feature: Feature | null
  onFeature: (f: Feature | null) => void
  /** Receives the map each time its layers are (re)built, so callers can add overlays. */
  onMap?: (map: MlMap | null, version: number) => void
}

export function MapView(props: Props) {
  const { state, retry } = useTown()
  const town = state.status === 'ready' ? state.town : null
  return (
    <section className={s.wrap} role="region" aria-label="Flood map, Kerr County">
      {state.status === 'loading' && (
        <Loading label="Loading the map">
          <div className={s.skeleton} />
        </Loading>
      )}
      {state.status === 'error' && (
        <div className={s.center}>
          <ErrorState what="Couldn't load road data" how={`${state.message} Check that the backend is running, then retry.`} onRetry={retry} />
        </div>
      )}
      {town && <MapCanvas town={town} {...props} />}
    </section>
  )
}

/** Restyle the shared case layer for the console: a plain dot, no pulse or halo. */
function quietSimLayers(map: MlMap, read: (n: string) => string) {
  for (const id of HIDDEN_SIM_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', 'none')
  if (!map.getLayer('case-dot')) return
  map.setPaintProperty('case-dot', 'circle-radius', ['case', ['get', 'selected'], 6, 4.5])
  map.setPaintProperty('case-dot', 'circle-color', read('--d-strong'))
  map.setPaintProperty('case-dot', 'circle-stroke-color', ['case', ['get', 'selected'], read('--d-info'), read('--d-bg')])
  map.setPaintProperty('case-dot', 'circle-stroke-width', ['case', ['get', 'selected'], 2.5, 1.5])
}

function popupHtml(name: string, stage: string, category: string): string {
  const esc = (x: string) => x.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)
  return `<div class="${s.tipName}">${esc(name)}</div><div class="${s.tipRow}"><span class="num">${esc(stage)}</span> · ${esc(category)}</div>`
}

function MapCanvas({ town, padding, wx, feature, onFeature, onMap }: Props & { town: Town }) {
  const store = useStore()
  const ref = useRef<HTMLDivElement>(null)
  const { map: liveMap, version, mode } = useMlMap(ref, town, 'dark', { bounds: START_BOUNDS, fitBoundsOptions: { padding: { top: 24, bottom: 24, left: padding.left + 8, right: 24 } } })
  const ready = version > 0
  const source = wx.load.status === 'ready' ? wx.load.source : null
  useEffect(() => {
    if (!onMap) return
    onMap(liveMap, version)
    return () => onMap(null, 0)
  }, [onMap, liveMap, version])
  const cases = useApp((a) => a.cases)
  const drones = useApp((a) => a.drones)
  const newest = useApp((a) => a.newestCaseId)
  const selected = useUi((u) => u.selectedCaseId)
  const onFeatureRef = useRef(onFeature)
  useEffect(() => {
    onFeatureRef.current = onFeature
  }, [onFeature])
  const snapRef = useRef(wx.snapshot)
  useEffect(() => {
    snapRef.current = wx.snapshot
  }, [wx.snapshot])

  // Dev only: lets the screenshot spec click a gauge at its projected position.
  useEffect(() => {
    if (!import.meta.env.DEV || !liveMap) return
    ;(window as unknown as { __flMap?: MlMap }).__flMap = liveMap
  }, [liveMap])

  // Build the console's layers each time the style (re)loads.
  useEffect(() => {
    if (!liveMap || !ready || !source || liveMap.getSource('wx-depth')) return
    const read = tokenReader(liveMap.getContainer())
    quietSimLayers(liveMap, read)
    addWxLayers(liveMap, source, read, liveMap.getLayer('flooded-glow') ? 'flooded-glow' : undefined)
  }, [liveMap, ready, version, source])

  const sel: WxSelection = useMemo(
    () => ({ gauge: feature?.kind === 'gauge' ? feature.site : null, road: feature?.kind === 'road' ? feature.edgeId : null }),
    [feature],
  )
  useEffect(() => {
    if (!liveMap || !ready || !wx.snapshot || !liveMap.getSource('wx-depth')) return
    updateWxLayers(liveMap, town, wx.snapshot, wx.layers, sel)
  }, [liveMap, ready, version, source, town, wx.snapshot, wx.layers, sel])

  useEffect(() => {
    if (ready && liveMap) setSource(liveMap, 'cases', casesFc(cases, selected))
  }, [ready, liveMap, version, cases, selected])

  // Clicks: a case, a gauge or a flooded road opens the detail panel; empty map closes it.
  useEffect(() => {
    const map = liveMap
    if (!map || !ready) return
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    const tip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, className: s.tip })
    const layers = ['case-dot', ...WX_CLICKABLE].filter((id) => map.getLayer(id))
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const f = map.queryRenderedFeatures(e.point, { layers })[0]
      if (!f) {
        onFeatureRef.current(null)
        store.setUi((u) => ({ ...u, selectedCaseId: null }))
        return
      }
      const p = f.properties ?? {}
      if (f.layer.id === 'case-dot') {
        onFeatureRef.current(null)
        store.setUi((u) => ({ ...u, selectedCaseId: p.id as string }))
      } else {
        store.setUi((u) => ({ ...u, selectedCaseId: null }))
        onFeatureRef.current(f.layer.id === 'wx-gauges' ? { kind: 'gauge', site: p.site as string } : { kind: 'road', edgeId: p.id as string })
      }
    }
    const onMove = (e: MapLayerMouseEvent) => {
      map.getCanvas().style.cursor = 'pointer'
      const site = e.features?.[0]?.properties?.site as string | undefined
      const g = snapRef.current?.gauges.find((x) => x.site === site)
      if (!g) return
      const stage = g.stageFt == null ? 'No reading' : `${g.stageFt.toFixed(1)} ft`
      tip.setLngLat([g.lon, g.lat]).setHTML(popupHtml(g.name, stage, CATEGORY_LABEL[g.stageFt == null ? 'none' : g.category])).addTo(map)
    }
    const onLeave = () => {
      map.getCanvas().style.cursor = ''
      tip.remove()
    }
    const enter = () => { map.getCanvas().style.cursor = 'pointer' }
    map.on('click', onClick)
    map.on('mousemove', 'wx-gauges', onMove)
    map.on('mouseleave', 'wx-gauges', onLeave)
    for (const id of ['case-dot', 'wx-roads-closed', 'wx-roads-likely']) {
      map.on('mouseenter', id, enter)
      map.on('mouseleave', id, onLeave)
    }
    return () => {
      tip.remove()
      map.off('click', onClick)
      map.off('mousemove', 'wx-gauges', onMove)
      map.off('mouseleave', 'wx-gauges', onLeave)
      for (const id of ['case-dot', 'wx-roads-closed', 'wx-roads-likely']) {
        map.off('mouseenter', id, enter)
        map.off('mouseleave', id, onLeave)
      }
    }
  }, [liveMap, ready, version, store])

  // Keep the visual centre clear of the panels.
  const pad = useMemo(() => ({ top: 16, bottom: padding.bottom, left: padding.left, right: padding.right }), [padding.left, padding.right, padding.bottom])
  const padRef = useRef(pad)
  useEffect(() => {
    padRef.current = pad
  }, [pad])
  useEffect(() => {
    if (!liveMap || liveMap.isMoving()) return
    liveMap.easeTo({ padding: pad, duration: reducedMotion() ? 0 : 300 })
  }, [liveMap, pad])

  // A new stalled car: fly to it.
  useEffect(() => {
    const map = liveMap
    const c = cases.find((x) => x.id === newest)
    if (!ready || !map || !c) return
    const center: [number, number] = [c.location.lon, c.location.lat]
    if (reducedMotion()) map.jumpTo({ center, zoom: FLY_ZOOM, padding: padRef.current })
    else map.flyTo({ center, zoom: FLY_ZOOM, padding: padRef.current, duration: 1800, essential: false })
  }, [ready, newest]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div ref={ref} className={s.map} />
      <span className={s.attrib}>
        {mode === 'offline' ? 'Basemap offline, showing bundled roads' : ATTRIBUTION}
        {source && ' · Rain: NOAA MRMS via Iowa Environmental Mesonet · Gauges: USGS, NWS'}
      </span>
      {liveMap && Object.values(drones).map((d) => <DroneMarker key={d.id} map={liveMap} lon={d.lon} lat={d.lat} trail={d.trail} returning={d.status === 'returning'} onScene={d.status === 'on_scene'} />)}
    </>
  )
}

/** HTML marker that glides between drone updates. */
function DroneMarker({ map, lon, lat, trail, returning, onScene }: { map: MlMap; lon: number; lat: number; trail: [number, number][]; returning: boolean; onScene: boolean }) {
  const markerRef = useRef<maplibregl.Marker | null>(null)
  const posRef = useRef<[number, number]>([lon, lat])

  useEffect(() => {
    const el = document.createElement('div')
    el.className = s.drone
    el.innerHTML = DRONE_SVG
    el.setAttribute('aria-hidden', 'true')
    const m = new maplibregl.Marker({ element: el, rotationAlignment: 'map' }).setLngLat(posRef.current).addTo(map)
    markerRef.current = m
    return () => { m.remove() }
  }, [map])

  useEffect(() => {
    const m = markerRef.current
    if (!m) return
    const from = posRef.current
    const to: [number, number] = [lon, lat]
    const prev = trail.length > 1 ? trail[trail.length - 2] : from
    if (prev[0] !== to[0] || prev[1] !== to[1]) m.setRotation(bearing(prev, to))
    m.getElement().classList.toggle(s.returning, returning)
    m.setOffset(onScene ? [14, -14] : [0, 0])
    if (reducedMotion()) {
      posRef.current = to
      m.setLngLat(to)
      return
    }
    let raf = 0
    const start = performance.now()
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / DRONE_ANIM_MS)
      const p: [number, number] = [from[0] + (to[0] - from[0]) * k, from[1] + (to[1] - from[1]) * k]
      posRef.current = p
      m.setLngLat(p)
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [lon, lat, trail, returning, onScene])

  return null
}
