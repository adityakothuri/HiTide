import { LngLatBounds } from 'maplibre-gl'
import { useEffect, useMemo, useRef } from 'react'
import type { SegmentState, Town } from '../data/types'
import { segmentIndex } from '../lib/geo'
import { ATTRIBUTION } from './basemap'
import { setSource } from './floodLayers'
import { EMPTY, floodedFc } from './mapData'
import { useMlMap } from './useMlMap'
import s from './MiniMap.module.css'

type Pt = [number, number]

interface Props {
  town: Town
  segments: Record<string, SegmentState>
  label: string
  route?: Pt[] | null
  hazardEdgeIds?: string[]
  /** The driver's car or position. */
  focus?: Pt | null
  /** Drone position, when one is flying to the car. */
  drone?: Pt | null
  height?: number
  /** Closest zoom when framing; lower it when the frame is a single point. */
  maxZoom?: number
}

const PAD = 36
const NO_IDS: string[] = []

/** Small, non-interactive map card for the phone: real streets, flood overlay, route and car. */
export function MiniMap({ town, segments, label, route, hazardEdgeIds = NO_IDS, focus, drone, height = 180, maxZoom = 16 }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const { map, version, mode } = useMlMap(ref, town, 'light', { interactive: false })

  // Callers often pass fresh arrays each render: key memos on primitive values instead.
  const hazardKey = hazardEdgeIds.join('|')
  const [fx, fy] = focus ?? [NaN, NaN]
  const [dx, dy] = drone ?? [NaN, NaN]
  const routeKey = route ? `${route.length}:${route[0]?.join(',')}:${route[route.length - 1]?.join(',')}` : ''
  // Keyed on the route's shape, not its identity.
  const stableRoute = useMemo(() => route, [routeKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const focusPt = useMemo<Pt | null>(() => (Number.isNaN(fx) ? null : [fx, fy]), [fx, fy])
  const dronePt = useMemo<Pt | null>(() => (Number.isNaN(dx) ? null : [dx, dy]), [dx, dy])

  const hazards = useMemo(() => {
    const idx = segmentIndex(town)
    return hazardKey ? hazardKey.split('|').map((id) => idx.get(id)).filter((f) => f !== undefined) : []
  }, [town, hazardKey])

  // Frame the route, hazard and car.
  const bounds = useMemo(() => {
    const pts: Pt[] = [...(stableRoute ?? []), ...hazards.flatMap((f) => f.geometry.coordinates as Pt[]), ...(focusPt ? [focusPt] : []), ...(dronePt ? [dronePt] : [])]
    if (pts.length === 0) return null
    const b = new LngLatBounds(pts[0], pts[0])
    for (const p of pts) b.extend(p)
    return b
  }, [stableRoute, hazards, focusPt, dronePt])

  useEffect(() => {
    if (!map || !version) return
    setSource(map, 'flooded', floodedFc(town, segments))
    setSource(map, 'reroutes', stableRoute && stableRoute.length > 1 ? { type: 'Feature', geometry: { type: 'LineString', coordinates: stableRoute }, properties: {} } : EMPTY)
    setSource(map, 'hazards', { type: 'FeatureCollection', features: hazards.map((f) => ({ type: 'Feature', geometry: f.geometry, properties: {} })) })
    setSource(map, 'focus', focusPt ? { type: 'Feature', geometry: { type: 'Point', coordinates: focusPt }, properties: {} } : EMPTY)
    setSource(map, 'cases', dronePt ? { type: 'Feature', geometry: { type: 'Point', coordinates: dronePt }, properties: { severity: 'info', selected: false } } : EMPTY)
  }, [map, version, town, segments, stableRoute, hazards, focusPt, dronePt])

  // Non-interactive map: keep the canvas out of the tab order.
  useEffect(() => {
    map?.getCanvas().setAttribute('tabindex', '-1')
  }, [map])

  useEffect(() => {
    if (!map || !version || !bounds) return
    map.fitBounds(bounds, { padding: PAD, maxZoom, animate: false })
  }, [map, version, bounds, maxZoom])

  return (
    <div className={s.wrap} style={{ height }}>
      <div ref={ref} className={s.map} role="img" aria-label={label} />
      {mode === 'tiles' ? <span className={s.attrib}>{ATTRIBUTION}</span> : <span className={s.attrib}>Map tiles offline</span>}
    </div>
  )
}
