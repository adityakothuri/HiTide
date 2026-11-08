import * as maplibregl from 'maplibre-gl'
import type { Map as MlMap, MapLayerMouseEvent } from 'maplibre-gl'
import { useEffect, useMemo, useRef } from 'react'
import type { Town } from '../data/types'
import { useTown } from '../hooks/useTown'
import { ATTRIBUTION, tokenReader } from '../map/basemap'
import { bearing, casesFc, driversFc, reroutesFc, trailsFc } from '../map/mapData'
import { setSource } from '../map/floodLayers'
import { addRegionLayers, REGION_CLICKABLE, REGION_CLUSTER, REGION_ROADS, updateRegionLayers, type RegionLayerData, type RegionPick } from '../map/regionLayers'
import { addRiskLayers, setStudyArea, updateRiskLayers } from '../map/riskLayer'
import { useMlMap } from '../map/useMlMap'
import { droneName } from '../region/derive'
import type { RiskIndex } from '../risk/grid'
import { readout } from '../risk/readout'
import type { LoadedFrame } from '../risk/useRiskGrid'
import { useScheme } from '../shell/scheme'
import { addWxLayers, updateWxLayers, WX_CLICKABLE, type WxSelection } from '../map/wxLayers'
import { useApp, useStore, useUi } from '../state/StoreContext'
import { ErrorState, Loading } from '../ui/States'
import { CATEGORY_LABEL } from '../wx/category'
import type { WxState } from '../wx/useWx'
import s from './MapView.module.css'

const DRONE_ANIM_MS = 600
const DRONE_STATUS = { idle: 'At base', flying: 'Flying', snapshot: 'Checking a crossing', returning: 'Returning' } as const
const ROAD_STATUS: Record<string, string> = { confirmed_flooded: 'Closed: confirmed flooded', likely_flooded: 'Likely flooded', unknown: 'Not checked yet' }
const FLY_ZOOM = 15
/** Hunt to Kerrville along the Guadalupe: every replay gauge and the town in view. */
const START_BOUNDS: [[number, number], [number, number]] = [[-99.36, 29.99], [-99.03, 30.105]]
/** Simulation layers the shared map adds that the console doesn't show; road status comes from the wx source. */
// Flooded roads come from the weather layer; the sim's own road and hazard lines would double them.
const HIDDEN_SIM_LAYERS = ['flooded-glow', 'flooded', 'case-pulse', 'hazards', 'reroutes-casing', 'focus', 'focus-halo']

export interface Padding { left: number; right: number; bottom: number }

/** Risk surface inputs: the grid index, the loaded frame for the current time, and the study-area polygon. */
export interface RiskInput { index: RiskIndex | null; current: LoadedFrame | null; area: GeoJSON.Polygon | null }
export type Feature = { kind: 'gauge'; site: string } | { kind: 'road'; edgeId: string }

/** Monitor page: the region situation (people, areas, critical points, drone fleet) replaces the town sim. */
export interface RegionMap {
  data: RegionLayerData
  onPick: (p: RegionPick | null) => void
  /** Where to centre when the pick changes. */
  focus: [number, number] | null
}

/** Town-sim layers the monitor hides when it shows the region situation instead. */
const TOWN_SIM_LAYERS = ['drivers', 'reroutes', 'trails', 'case-halo', 'case-dot']

function reducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

const DRONE_SVG =
  '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 3l6 16-6-4-6 4z" fill="currentColor" stroke="white" stroke-width="1.5" stroke-linejoin="round"/></svg>'

interface Props {
  padding: Padding
  wx: WxState
  feature: Feature | null
  onFeature: (f: Feature | null) => void
  risk?: RiskInput
  /** Receives the map each time its layers are (re)built, so callers can add overlays. */
  onMap?: (map: MlMap | null, version: number) => void
  region?: RegionMap
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

/** Console styling for the shared sim layers: severity-coloured case dots with a halo, quiet driver dots. */
function quietSimLayers(map: MlMap, read: (n: string) => string) {
  for (const id of HIDDEN_SIM_LAYERS) if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', 'none')
  if (!map.getLayer('case-dot')) return
  map.setPaintProperty('case-dot', 'circle-radius', ['case', ['get', 'selected'], 7, 5.5])
  map.setPaintProperty('case-dot', 'circle-stroke-color', read('--map-halo'))
  map.setPaintProperty('case-dot', 'circle-stroke-width', 2)
  if (map.getLayer('reroutes')) {
    map.setPaintProperty('reroutes', 'line-width', ['interpolate', ['linear'], ['zoom'], 11, 1, 15, 2.5])
    map.setPaintProperty('reroutes', 'line-opacity', 0.55)
    map.setPaintProperty('reroutes', 'line-dasharray', [2, 1.5])
  }
  if (map.getLayer('drivers')) {
    map.setPaintProperty('drivers', 'circle-color', ['case', ['get', 'stopped'], read('--caution-mark'), read('--accent')])
    map.setPaintProperty('drivers', 'circle-radius', ['interpolate', ['linear'], ['zoom'], 10, 2.5, 14, 5, 16, 6])
    map.setPaintProperty('drivers', 'circle-opacity', 0.9)
    map.setPaintProperty('drivers', 'circle-stroke-color', read('--map-halo'))
    map.setPaintProperty('drivers', 'circle-stroke-width', 1)
  }
}

function popupHtml(name: string, stage: string, category: string): string {
  const esc = (x: string) => x.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)
  return `<div class="${s.tipName}">${esc(name)}</div><div class="${s.tipRow}"><span class="num">${esc(stage)}</span> · ${esc(category)}</div>`
}

function roadTipHtml(name: string, status: string): string {
  const esc = (x: string) => x.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)
  return `<div class="${s.tipName}">${esc(name)}</div><div class="${s.tipRow}">${esc(status)}</div>`
}

function riskTipHtml(value: number, bandName: string, factors: string[]): string {
  const esc = (x: string) => x.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)
  const why = factors.length ? `<div class="${s.tipRow}">${factors.map(esc).join(', ')}</div>` : ''
  return `<div class="${s.tipName}"><span class="num">${value}</span> · ${esc(bandName)} risk</div>${why}`
}

function MapCanvas({ town, padding, wx, feature, onFeature, onMap, risk, region }: Props & { town: Town }) {
  const hasRegion = region !== undefined
  const store = useStore()
  const ref = useRef<HTMLDivElement>(null)
  const scheme = useScheme()
  const { map: liveMap, version, mode } = useMlMap(ref, town, scheme, { bounds: START_BOUNDS, fitBoundsOptions: { padding: { top: 24, bottom: 24, left: padding.left + 8, right: 24 } } })
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
    if (hasRegion) for (const id of TOWN_SIM_LAYERS) if (liveMap.getLayer(id)) liveMap.setLayoutProperty(id, 'visibility', 'none')
    addWxLayers(liveMap, source, read, liveMap.getLayer('flooded-glow') ? 'flooded-glow' : undefined)
    addRiskLayers(liveMap, read, 'wx-rain-p1h')
    if (hasRegion) addRegionLayers(liveMap, read)
  }, [liveMap, ready, version, source, hasRegion])

  // Region situation: redraw on every poll.
  const regionData = region?.data
  useEffect(() => {
    if (!liveMap || !ready || !regionData || !liveMap.getSource('rg-points')) return
    updateRegionLayers(liveMap, regionData)
  }, [liveMap, ready, version, source, regionData])
  const onPickRef = useRef(region?.onPick)
  useEffect(() => {
    onPickRef.current = region?.onPick
  }, [region?.onPick])

  // Fit the whole region once its bounds arrive.
  const fitted = useRef(false)
  const bbox = region?.data.info?.bbox
  useEffect(() => {
    if (!liveMap || !ready || !bbox || fitted.current) return
    fitted.current = true
    liveMap.fitBounds([[bbox.west, bbox.south], [bbox.east, bbox.north]], { padding: padRef.current, duration: 0 })
  }, [liveMap, ready, bbox]) // eslint-disable-line react-hooks/exhaustive-deps

  // Centre on whatever was picked in a list, keeping the current zoom unless it is too far out.
  const focus = region?.focus
  useEffect(() => {
    if (!liveMap || !ready || !focus) return
    const zoom = Math.max(liveMap.getZoom(), 12.5)
    if (reducedMotion()) liveMap.jumpTo({ center: focus, zoom, padding: padRef.current })
    else liveMap.easeTo({ center: focus, zoom, padding: padRef.current, duration: 700 })
  }, [liveMap, ready, focus?.[0], focus?.[1]]) // eslint-disable-line react-hooks/exhaustive-deps

  // Risk surface: frame, opacity and visibility follow the base field.
  const riskRef = useRef(risk)
  useEffect(() => {
    riskRef.current = risk
  }, [risk])
  const layersRef = useRef(wx.layers)
  useEffect(() => {
    layersRef.current = wx.layers
  }, [wx.layers])
  useEffect(() => {
    if (!liveMap || !ready || !liveMap.getSource('wx-depth')) return
    setStudyArea(liveMap, risk?.area ?? null)
  }, [liveMap, ready, version, source, risk?.area])
  useEffect(() => {
    if (!liveMap || !ready || !liveMap.getSource('wx-depth')) return
    updateRiskLayers(liveMap, {
      visible: wx.layers.base === 'risk',
      opacity: wx.layers.opacity,
      idx: risk?.index ?? null,
      values: risk?.current?.values ?? null,
      frameId: risk?.current?.frame.id ?? null,
      reducedMotion: reducedMotion(),
    })
  }, [liveMap, ready, version, source, wx.layers.base, wx.layers.opacity, risk?.index, risk?.current])

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

  // The synthetic fleet: every simulated driver, active reroutes, and drone flight paths.
  const drivers = useApp((a) => a.drivers)
  const reroutes = useApp((a) => a.reroutes)
  const caseDrivers = useMemo(() => new Set(cases.filter((c) => c.state !== 'resolved').map((c) => c.driver_id)), [cases])
  useEffect(() => {
    if (!ready || !liveMap) return
    setSource(liveMap, 'drivers', driversFc(drivers, caseDrivers))
    setSource(liveMap, 'reroutes', reroutesFc(reroutes))
    setSource(liveMap, 'trails', trailsFc(drones))
  }, [ready, liveMap, version, drivers, caseDrivers, reroutes, drones])


  // Clicks: a case, a gauge or a flooded road opens the detail panel; empty map closes it.
  useEffect(() => {
    const map = liveMap
    if (!map || !ready) return
    const nav = new maplibregl.NavigationControl({ showCompass: false })
    const scale = new maplibregl.ScaleControl({ maxWidth: 120, unit: 'imperial' })
    map.addControl(nav, 'top-right')
    map.addControl(scale, 'bottom-right')
    const tip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, className: s.tip })
    const riskTip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: s.tip })
    const roadTip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8, className: s.tip })
    const onRiskMove = (e: maplibregl.MapMouseEvent) => {
      const r = riskRef.current
      if (layersRef.current.base !== 'risk' || !r?.index || !r.current) {
        riskTip.remove()
        return
      }
      if (map.queryRenderedFeatures(e.point, { layers: ['wx-gauges'].filter((id) => map.getLayer(id)) }).length) {
        riskTip.remove()
        return
      }
      const out = readout(r.index, r.current.values, r.current.factors, e.lngLat.lng, e.lngLat.lat)
      if (!out) {
        riskTip.remove()
        return
      }
      riskTip.setLngLat(e.lngLat).setHTML(riskTipHtml(out.value, out.band, out.factors)).addTo(map)
    }
    const onRiskOut = () => riskTip.remove()
    map.on('mousemove', onRiskMove)
    map.getCanvas().addEventListener('mouseleave', onRiskOut)
    const onClick = (e: maplibregl.MapMouseEvent) => {
      // Looked up per click: the wx layers may be added after this effect runs (slow live source).
      // A people cluster: zoom in until it splits.
      const cluster = map.getLayer(REGION_CLUSTER) ? map.queryRenderedFeatures(e.point, { layers: [REGION_CLUSTER] })[0] : undefined
      if (cluster && cluster.geometry.type === 'Point') {
        const src = map.getSource('rg-people') as maplibregl.GeoJSONSource
        const center = cluster.geometry.coordinates as [number, number]
        void src.getClusterExpansionZoom(Number(cluster.properties?.cluster_id)).then((zoom) => {
          map.easeTo({ center, zoom: zoom + 0.25, padding: padRef.current, duration: reducedMotion() ? 0 : 500 })
        })
        return
      }
      const regionHit = map.queryRenderedFeatures(e.point, { layers: REGION_CLICKABLE.filter((id) => map.getLayer(id)) })[0]
      const roadHit = regionHit ? undefined : map.queryRenderedFeatures(e.point, { layers: REGION_ROADS.filter((id) => map.getLayer(id)) })[0]
      if (roadHit) {
        const p = roadHit.properties ?? {}
        roadTip.setLngLat(e.lngLat).setHTML(roadTipHtml(String(p.name ?? 'Unnamed road'), ROAD_STATUS[String(p.status)] ?? String(p.status))).addTo(map)
        return
      }
      roadTip.remove()
      if (regionHit && onPickRef.current) {
        const id = String(regionHit.properties?.id ?? '')
        const layer = regionHit.layer.id
        const kind = layer === 'rg-people' ? 'person' : layer.startsWith('rg-areas') ? 'area' : 'point'
        onFeatureRef.current(null)
        onPickRef.current({ kind, id })
        return
      }
      const layers = ['case-dot', ...WX_CLICKABLE].filter((id) => map.getLayer(id))
      const f = map.queryRenderedFeatures(e.point, { layers })[0]
      if (!f) {
        onPickRef.current?.(null)
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
    for (const id of ['case-dot', 'wx-roads-closed', 'wx-roads-likely', ...REGION_CLICKABLE, ...REGION_ROADS, REGION_CLUSTER]) {
      map.on('mouseenter', id, enter)
      map.on('mouseleave', id, onLeave)
    }
    return () => {
      tip.remove()
      riskTip.remove()
      roadTip.remove()
      map.off('mousemove', onRiskMove)
      map.getCanvas().removeEventListener('mouseleave', onRiskOut)
      map.removeControl(nav)
      map.removeControl(scale)
      map.off('click', onClick)
      map.off('mousemove', 'wx-gauges', onMove)
      map.off('mouseleave', 'wx-gauges', onLeave)
      for (const id of ['case-dot', 'wx-roads-closed', 'wx-roads-likely', ...REGION_CLICKABLE, ...REGION_ROADS, REGION_CLUSTER]) {
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
    if (!ready || !map || !c || hasRegion) return
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
      {liveMap && !hasRegion && Object.values(drones).map((d) => <DroneMarker key={d.id} map={liveMap} lon={d.lon} lat={d.lat} trail={d.trail} returning={d.status === 'returning'} onScene={d.status === 'on_scene'} />)}
      {liveMap && region?.data.drones.map((d) => (
        <DroneMarker
          key={d.id}
          map={liveMap}
          lon={d.lon}
          lat={d.lat}
          trail={region.data.trails[d.id] ?? []}
          returning={d.status === 'returning'}
          onScene={false}
          fleet
          parked={d.status === 'idle'}
          label={`${droneName(d)} · ${DRONE_STATUS[d.status]} · battery ${Math.round(d.battery_pct)}%`}
        />
      ))}
    </>
  )
}

/** HTML marker that glides between drone updates. */
function DroneMarker({ map, lon, lat, trail, returning, onScene, fleet = false, parked = false, label }: { map: MlMap; lon: number; lat: number; trail: [number, number][]; returning: boolean; onScene: boolean; fleet?: boolean; parked?: boolean; label?: string }) {
  const markerRef = useRef<maplibregl.Marker | null>(null)
  const posRef = useRef<[number, number]>([lon, lat])

  useEffect(() => {
    const el = document.createElement('div')
    el.className = fleet ? `${s.drone} ${s.fleet}` : s.drone
    el.innerHTML = DRONE_SVG
    el.setAttribute('aria-hidden', 'true')
    const m = new maplibregl.Marker({ element: el, rotationAlignment: 'map' }).setLngLat(posRef.current).addTo(map)
    markerRef.current = m
    return () => { m.remove() }
  }, [map, fleet])

  useEffect(() => {
    const m = markerRef.current
    if (!m) return
    const from = posRef.current
    const to: [number, number] = [lon, lat]
    const prev = trail.length > 1 ? trail[trail.length - 2] : from
    if (prev[0] !== to[0] || prev[1] !== to[1]) m.setRotation(bearing(prev, to))
    m.getElement().classList.toggle(s.returning, returning)
    m.getElement().classList.toggle(s.parked, parked)
    if (label) m.getElement().title = label
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
  }, [lon, lat, trail, returning, onScene, parked, label])

  return null
}
