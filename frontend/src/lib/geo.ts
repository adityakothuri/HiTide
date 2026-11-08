import type { SegmentProps, Town } from '../data/types'

type SegFeature = GeoJSON.Feature<GeoJSON.LineString, SegmentProps>

const indexCache = new WeakMap<Town, Map<string, SegFeature>>()

/** edge_id -> feature, built once per town. */
export function segmentIndex(town: Town): Map<string, SegFeature> {
  let idx = indexCache.get(town)
  if (!idx) {
    idx = new Map(town.segments.features.map((f) => [f.properties.edge_id, f]))
    indexCache.set(town, idx)
  }
  return idx
}

export function streetOf(town: Town | null, edgeId: string): string | null {
  if (!town) return null
  return segmentIndex(town).get(edgeId)?.properties.name ?? null
}

/** Name of the named street closest to a point. Cheap equirectangular distance is fine at town scale. */
export function nearestStreet(town: Town | null, lat: number, lon: number): string | null {
  if (!town) return null
  const k = Math.cos((lat * Math.PI) / 180)
  let best: string | null = null
  let bestD = Infinity
  for (const f of town.segments.features) {
    const name = f.properties.name
    if (!name) continue
    for (const [x, y] of f.geometry.coordinates) {
      const d = ((x - lon) * k) ** 2 + (y - lat) ** 2
      if (d < bestD) {
        bestD = d
        best = name
      }
    }
  }
  return best
}

/** Street named in backend copy like "...flooded roads at Riverside Drive." */
export function streetFromText(text: string | undefined): string | null {
  if (!text) return null
  const m = /\b(?:at|on) ([A-Z][\w.' ]+?(?:Street|St|Drive|Dr|Road|Rd|Lane|Ln|Avenue|Ave|Highway|Hwy|Boulevard|Blvd|Loop|Way|Parkway|Pkwy|Trail|Court|Ct))\b/.exec(text)
  return m ? m[1] : null
}
