import type { LngLat } from './types';

/** Small, pure geometry helpers for routes drawn from the cached Kerrville graph. Accurate enough at town scale. */

const M_PER_DEG = 111_320;

export function distanceM(a: LngLat, b: LngLat): number {
  const midLat = ((a[1] + b[1]) / 2) * (Math.PI / 180);
  const dx = (a[0] - b[0]) * M_PER_DEG * Math.cos(midLat);
  const dy = (a[1] - b[1]) * M_PER_DEG;
  return Math.hypot(dx, dy);
}

/** Index of the route vertex closest to a point. Returns 0 for an empty route. */
export function nearestIndex(coords: readonly LngLat[], point: LngLat): number {
  let best = 0;
  let bestD = Infinity;
  coords.forEach((c, i) => {
    const d = distanceM(c, point);
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  });
  return best;
}

/** The point `meters` further along the route from vertex `fromIndex`, clamped to the route's end. */
export function pointAlong(coords: readonly LngLat[], fromIndex: number, meters: number): LngLat {
  if (coords.length === 0) throw new RangeError('pointAlong needs a non-empty route');
  let i = Math.max(0, Math.min(fromIndex, coords.length - 1));
  let left = Math.max(0, meters);
  while (i < coords.length - 1) {
    const seg = distanceM(coords[i], coords[i + 1]);
    if (seg >= left && seg > 0) {
      const f = left / seg;
      const [x0, y0] = coords[i];
      const [x1, y1] = coords[i + 1];
      return [x0 + (x1 - x0) * f, y0 + (y1 - y0) * f];
    }
    left -= seg;
    i += 1;
  }
  return coords[coords.length - 1];
}

/** Route vertices from `fromIndex` onward, re-sampled so consecutive points are about `stepM` apart. */
export function sampleAlong(coords: readonly LngLat[], stepM: number, fromIndex = 0, toIndex = coords.length - 1): LngLat[] {
  if (coords.length === 0) return [];
  const from = Math.max(0, Math.min(fromIndex, coords.length - 1));
  const to = Math.max(from, Math.min(toIndex, coords.length - 1));
  const out: LngLat[] = [coords[from]];
  let carried = 0;
  for (let i = from + 1; i <= to; i += 1) {
    carried += distanceM(coords[i - 1], coords[i]);
    if (carried >= stepM || i === to) {
      out.push(coords[i]);
      carried = 0;
    }
  }
  return out;
}
