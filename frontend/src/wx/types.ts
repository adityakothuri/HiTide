/** Hydromet layers for the ops map. One interface, two sources: the July 4, 2025 replay now, live feeds later. */

export type RainProduct = 'p1h' | 'p24h'
export type FloodCategory = 'below' | 'action' | 'minor' | 'moderate' | 'major' | 'none'
export type WxMode = 'replay' | 'live'

export interface ColorStop { pos: number; color: string }
export interface Tick { pos: number; label: string }
export interface RampLegend { stops: ColorStop[]; ticks: Tick[]; units: string }

export interface CategoryStages { action: number; minor: number; moderate: number; major: number }

export interface GaugeReading {
  site: string
  name: string
  lon: number
  lat: number
  /** null when the gauge has no reading near this time (offline, or the record ends). */
  stageFt: number | null
  /** ft per hour over the last hour, null without two readings. */
  trendFtPerHr: number | null
  category: FloodCategory
  categories: CategoryStages | null
  /** [epoch ms, ft] across the whole window, for sparklines. */
  series: readonly (readonly [number, number])[]
}

/** Corners for a MapLibre image source: top-left, top-right, bottom-right, bottom-left. */
export type Quad = [[number, number], [number, number], [number, number], [number, number]]

export interface DepthFrame { url: string; coordinates: Quad; riseM: number }
export interface DepthBand { label: string; color: string }

export interface WxWarning { event: string; area: string; issuedAt: number }

export interface RoadStatus { closed: ReadonlySet<string>; likely: ReadonlySet<string> }

export interface WxSnapshot {
  t: number
  /** Tile URL template for the rain layer at t, or null if no data. */
  rainTiles: (product: RainProduct) => string | null
  /** The hour the rain layer shows (end of the accumulation window), epoch ms. */
  rainValidAt: number | null
  gauges: GaugeReading[]
  depth: DepthFrame | null
  roads: RoadStatus
  /** The most recent NWS warning in effect at t, if any. */
  warning: WxWarning | null
}

export interface WxSource {
  mode: WxMode
  /** Footer note, e.g. "Demo data · replay of July 4, 2025". */
  note: string
  /** Scrubbable window, epoch ms. */
  range: [number, number]
  stepMs: number
  rain: { products: Record<RainProduct, { label: string; legend: RampLegend }>; minzoom: number; maxzoom: number; bounds: [number, number, number, number] }
  depthBands: DepthBand[]
  /** NWS warnings issued in the window, oldest first (marked on the time slider). */
  warnings: WxWarning[]
  at(t: number): WxSnapshot
}
