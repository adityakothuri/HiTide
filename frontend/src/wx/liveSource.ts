import { loadReplayData, replaySource } from './replaySource'
import type { RainProduct, WxSource } from './types'

/**
 * Live hydromet source (DATA_MODE=real). Same WxSource as the replay, so the console needs no other changes.
 *
 * It reuses the replay builder with live inputs:
 *  - gauge: the Kerrville USGS stage, last 24 h, from the backend's /api/feeds (live, or its cache)
 *  - depth frames and road thresholds: the replay's precomputed frames, indexed by today's river rise
 *  - warnings: active NWS alerts from /api/feeds
 *  - rain: IEM's live MRMS tiles (latest hour / 24 h; same colour ramps as the archived tiles)
 */

const WINDOW_MS = 6 * 3_600_000
const STEP_MS = 15 * 60_000
const KERRVILLE = '08166200'
const IEM_TILES: Record<RainProduct, string> = {
  p1h: 'https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/q2-n1p-900913/{z}/{x}/{y}.png',
  p24h: 'https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/q2-p24h-900913/{z}/{x}/{y}.png',
}

interface LiveFeeds {
  nws_alerts?: { source?: string; alerts?: { event: string | null; headline: string | null; onset: string | null }[] }
  usgs_gage?: { source?: string; series_24h?: { time: string | null; value_ft: number }[] }
}

function areaOf(headline: string | null): string {
  return (headline && /for ([A-Z][\w ]*?County)/.exec(headline)?.[1]) || 'Kerr County'
}

export async function loadLiveSource(): Promise<WxSource> {
  const res = await fetch('/api/feeds')
  if (!res.ok) throw new Error(`Live feeds unavailable (${res.status})`)
  const [feeds, replay] = await Promise.all([res.json() as Promise<LiveFeeds>, loadReplayData()])

  const kerr = replay.gauges.gauges.find((g) => g.site === KERRVILLE)
  const series = (feeds.usgs_gage?.series_24h ?? [])
    .filter((p): p is { time: string; value_ft: number } => !!p.time)
    .map((p) => [p.time, p.value_ft] as [string, number])
  const warnings = (feeds.nws_alerts?.alerts ?? [])
    .filter((a) => a.event && a.onset)
    .map((a) => ({ at: a.onset as string, event: a.event as string, area: areaOf(a.headline) }))

  const base = replaySource({
    mrms: { ...replay.mrms, stamps_utc: [] },
    depth: replay.depth,
    gauges: {
      warnings,
      gauges: kerr ? [{ ...kerr, series }] : [],
    },
  })

  const end = Math.floor(Date.now() / STEP_MS) * STEP_MS
  const usgs = feeds.usgs_gage?.source === 'live' ? 'USGS live' : `USGS ${feeds.usgs_gage?.source ?? 'unavailable'}`
  return {
    ...base,
    mode: 'live',
    note: `Live data · ${usgs}, NWS alerts, MRMS rain (IEM)`,
    range: [end - WINDOW_MS, end],
    stepMs: STEP_MS,
    at(t) {
      return { ...base.at(t), rainTiles: (p) => IEM_TILES[p], rainValidAt: end }
    },
  }
}
