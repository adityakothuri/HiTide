import { useEffect, useState } from 'react'

/** Study-area polygon (public/grids/study_area.geojson): accepts a Polygon, Feature or FeatureCollection. */
export function polygonOf(raw: unknown): GeoJSON.Polygon | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as { type?: string; geometry?: unknown; features?: unknown[]; coordinates?: unknown }
  if (o.type === 'Polygon' && Array.isArray(o.coordinates)) return o as GeoJSON.Polygon
  if (o.type === 'Feature') return polygonOf(o.geometry)
  if (o.type === 'FeatureCollection' && Array.isArray(o.features)) return polygonOf(o.features[0])
  if (o.type === 'MultiPolygon' && Array.isArray(o.coordinates)) {
    const first = (o.coordinates as unknown[])[0]
    return Array.isArray(first) ? { type: 'Polygon', coordinates: first as GeoJSON.Position[][] } : null
  }
  return null
}

export function useStudyArea(): GeoJSON.Polygon | null {
  const [area, setArea] = useState<GeoJSON.Polygon | null>(null)
  useEffect(() => {
    let alive = true
    fetch(`${(import.meta.env.BASE_URL ?? '/').replace(/\/$/, '')}/grids/study_area.geojson`)
      .then((r) => (r.ok ? r.json() : null))
      .then((j: unknown) => alive && setArea(polygonOf(j)))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])
  return area
}
