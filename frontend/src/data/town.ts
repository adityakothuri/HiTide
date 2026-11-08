import type { SegmentProps, Town } from './types'

type Lines = GeoJSON.FeatureCollection<GeoJSON.LineString, SegmentProps>

function boundsOf(fc: Lines): [number, number, number, number] {
  let [w, s, e, n] = [Infinity, Infinity, -Infinity, -Infinity]
  for (const f of fc.features) {
    for (const [x, y] of f.geometry.coordinates) {
      w = Math.min(w, x); s = Math.min(s, y); e = Math.max(e, x); n = Math.max(n, y)
    }
  }
  return [w, s, e, n]
}

/** Loads the bundled offline town cache from /town (copied from data/town by `npm run sync-town`). */
export async function loadStaticTown(): Promise<Town> {
  const [segRes, riverRes] = await Promise.all([fetch('/town/segments.geojson'), fetch('/town/river.geojson')])
  if (!segRes.ok || !riverRes.ok) throw new Error('The offline town data is missing. Run "npm run sync-town" and reload.')
  const segments = (await segRes.json()) as Lines
  const river = (await riverRes.json()) as Town['river']
  const bounds = boundsOf(segments)
  return { segments, river, bounds, center: [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2] }
}
