import { categoryOf, sampleSeries } from './category'
import type { CategoryStages, DepthBand, GaugeReading, Quad, RainProduct, RampLegend, WxSource } from './types'

/**
 * July 4, 2025 replay from the cached files in /wx (built by backend/scripts/*wx* and `npm run sync-wx`).
 * Everything is computed in the browser, so the slider can scrub freely and the demo runs offline.
 */

const FT_TO_M = 0.3048
const HOUR_MS = 3_600_000
const STEP_MS = 5 * 60_000
const MAX_GAP_MS = 30 * 60_000
/** Replay window: 01:00 to 07:30 CDT. */
export const REPLAY_RANGE: [number, number] = [Date.parse('2025-07-04T06:00:00Z'), Date.parse('2025-07-04T12:30:00Z')]
const KERRVILLE = '08166200'

interface MrmsManifest {
  bbox: [number, number, number, number]
  minzoom: number
  maxzoom: number
  stamps_utc: string[]
  products: Record<RainProduct, { label: string; legend: RampLegend }>
}

interface DepthManifest {
  gauge: { site: string; base_stage_ft: number }
  rise_step_m: number
  coordinates: Quad
  bands: DepthBand[]
  frames: { rise_m: number; file: string }[]
  roads: Record<string, [number, number]>
}

interface GaugesFile {
  warnings?: { at: string; event: string; area: string }[]
  gauges: { site: string; name: string; lon: number; lat: number; categories_ft: CategoryStages | null; series: [string, number][] }[]
}

export interface ReplayData { mrms: MrmsManifest; depth: DepthManifest; gauges: GaugesFile }

function stampMs(stamp: string): number {
  return Date.UTC(+stamp.slice(0, 4), +stamp.slice(4, 6) - 1, +stamp.slice(6, 8), +stamp.slice(8, 10))
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Replay data missing (${url}). Run "npm run sync-wx" and reload.`)
  return (await res.json()) as T
}

export async function loadReplaySource(): Promise<WxSource> {
  const [mrms, depth, gauges] = await Promise.all([
    getJson<MrmsManifest>('/wx/mrms/manifest.json'),
    getJson<DepthManifest>('/wx/depth/manifest.json'),
    getJson<GaugesFile>('/wx/gauges.json'),
  ])
  return replaySource({ mrms, depth, gauges })
}

/** Pure: builds the source from already-loaded files (tested directly). */
export function replaySource({ mrms, depth, gauges }: ReplayData): WxSource {
  const stamps = mrms.stamps_utc.map((s) => ({ s, ms: stampMs(s) }))
  const sites = gauges.gauges.map((g) => ({ ...g, ms: g.series.map(([iso, v]) => [Date.parse(iso), v] as const) }))
  const kerrville = sites.find((g) => g.site === depth.gauge.site || g.site === KERRVILLE)
  const roads = Object.entries(depth.roads)
  const lastFrame = depth.frames.length - 1
  const warnings = (gauges.warnings ?? [])
    .map((w) => ({ event: w.event, area: w.area, issuedAt: Date.parse(w.at) }))
    .sort((a, b) => a.issuedAt - b.issuedAt)

  /** The newest completed hour at or before t (MRMS accumulations are stamped at their end). */
  const rainStamp = (t: number) => [...stamps].reverse().find((x) => x.ms <= t) ?? stamps[0] ?? null

  const riseAt = (t: number): number => {
    const stage = kerrville ? sampleSeries(kerrville.ms, t, MAX_GAP_MS) : null
    return stage == null ? 0 : Math.max(0, (stage - depth.gauge.base_stage_ft) * FT_TO_M)
  }

  return {
    mode: 'replay',
    note: 'Demo data · replay of July 4, 2025',
    range: REPLAY_RANGE,
    stepMs: STEP_MS,
    rain: { products: mrms.products, minzoom: mrms.minzoom, maxzoom: mrms.maxzoom, bounds: mrms.bbox },
    depthBands: depth.bands,
    warnings,
    at(t) {
      const stamp = rainStamp(t)
      const rise = riseAt(t)
      const k = Math.min(lastFrame, Math.floor(rise / depth.rise_step_m + 1e-9))
      const frame = depth.frames[k]
      const closed = new Set<string>()
      const likely = new Set<string>()
      for (const [id, [likelyAt, closedAt]] of roads) {
        if (rise <= 0) break
        if (rise >= closedAt) closed.add(id)
        else if (rise >= likelyAt) likely.add(id)
      }
      const readings: GaugeReading[] = sites.map((g) => {
        const stageFt = sampleSeries(g.ms, t, MAX_GAP_MS)
        const before = sampleSeries(g.ms, t - HOUR_MS, MAX_GAP_MS)
        return {
          site: g.site,
          name: g.name,
          lon: g.lon,
          lat: g.lat,
          stageFt,
          trendFtPerHr: stageFt != null && before != null ? stageFt - before : null,
          category: categoryOf(stageFt, g.categories_ft),
          categories: g.categories_ft,
          series: g.ms,
        }
      })
      return {
        t,
        rainTiles: (p) => (stamp ? `/wx/mrms/${p}/${stamp.s}/{z}/{x}/{y}.png` : null),
        rainValidAt: stamp?.ms ?? null,
        gauges: readings,
        depth: frame && k > 0 ? { url: `/wx/depth/${frame.file}`, coordinates: depth.coordinates, riseM: frame.rise_m } : null,
        roads: { closed, likely },
        warning: [...warnings].reverse().find((w) => w.issuedAt <= t) ?? null,
      }
    },
  }
}
