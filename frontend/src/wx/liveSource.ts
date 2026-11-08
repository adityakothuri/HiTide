import type { WxSource } from './types'

/**
 * Live hydromet source: not connected yet.
 *
 * TODO(live): implement when the partner's API keys and data arrive. It returns the same WxSource as
 * the replay, so the console needs no other changes:
 *  - range: the last 6 h to now; at(t) for t = now uses the latest values.
 *  - rain tiles: IEM live MRMS, https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/q2-n1p-900913/{z}/{x}/{y}.png
 *    and q2-p24h-900913 (same color ramps as the archived tiles, so the legend is unchanged).
 *  - gauges: USGS Water Data stage (backend /api/feeds) plus NWS NWPS flood categories.
 *  - depth / roads: the backend's live river level through the same depth frames.
 */
export async function loadLiveSource(): Promise<WxSource> {
  throw new Error('Live hydromet feeds are not connected yet. Set VITE_WX_MODE=replay to use the July 4, 2025 replay.')
}
