/**
 * Flood risk index frames written by backend/scripts/build_risk_grid.py into public/grids/.
 * index.json describes the grid; each frame is Float32 little-endian, row-major, row 0 = north, NaN outside.
 * A sibling .factors.bin holds one byte per cell: (top factor << 4) | second factor, 255 = none.
 */
export type FrameKind = 'observed' | 'forecast'

export interface RiskFrame {
  id: string
  t: number
  kind: FrameKind
  url: string
  factorsUrl: string
  min: number
  max: number
  /** Study-area max and mean of the past hour's rain, inches (optional; older indexes lack them). */
  rain1hMax: number | null
  rain1hMean: number | null
}

export interface RiskIndex {
  name: string
  studyArea: string
  /** Cell-edge bounds: west, south, east, north (degrees). */
  bounds: [number, number, number, number]
  width: number
  height: number
  cellM: number
  factors: string[]
  frames: RiskFrame[]
}

function fail(msg: string): never {
  throw new Error(`Risk grid index: ${msg}`)
}

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const isStr = (v: unknown): v is string => typeof v === 'string' && v.length > 0

/** Validates untrusted JSON from public/grids/index.json. */
export function parseIndex(raw: unknown): RiskIndex {
  if (!raw || typeof raw !== 'object') fail('not an object')
  const o = raw as Record<string, unknown>
  const b = o.bounds
  if (!Array.isArray(b) || b.length !== 4 || !b.every(isNum)) fail('bounds must be [west, south, east, north]')
  const [w, s, e, n] = b as number[]
  if (!(e > w && n > s)) fail('bounds are inverted')
  const width = o.width
  const height = o.height
  if (!isNum(width) || !isNum(height) || width < 1 || height < 1 || !Number.isInteger(width) || !Number.isInteger(height)) fail('bad size')
  if (!Array.isArray(o.factors) || !o.factors.every(isStr)) fail('factors must be strings')
  if (!Array.isArray(o.frames) || o.frames.length === 0) fail('no frames')
  const frames = o.frames.map((f: unknown): RiskFrame => {
    const r = (f ?? {}) as Record<string, unknown>
    const t = typeof r.time === 'string' ? Date.parse(r.time) : NaN
    if (!isStr(r.id) || !isStr(r.url) || !isStr(r.factors_url) || !Number.isFinite(t)) fail('frame is missing id, url or time')
    if (r.kind !== 'observed' && r.kind !== 'forecast') fail(`frame ${String(r.id)} has an unknown kind`)
    return { id: r.id, t, kind: r.kind, url: r.url, factorsUrl: r.factors_url, min: isNum(r.min) ? r.min : 0, max: isNum(r.max) ? r.max : 100, rain1hMax: isNum(r.rain1h_max) ? r.rain1h_max : null, rain1hMean: isNum(r.rain1h_mean) ? r.rain1h_mean : null }
  })
  return {
    name: isStr(o.name) ? o.name : 'Flood risk index',
    studyArea: isStr(o.study_area) ? o.study_area : '',
    bounds: [w, s, e, n],
    width,
    height,
    cellM: isNum(o.cell_m) ? o.cell_m : 0,
    factors: o.factors as string[],
    frames: [...frames].sort((a, c) => a.t - c.t),
  }
}

export function decodeFrame(buf: ArrayBuffer, width: number, height: number): Float32Array {
  const n = width * height
  if (buf.byteLength !== n * 4) throw new Error(`Risk frame: expected ${n * 4} bytes, got ${buf.byteLength}`)
  const dv = new DataView(buf)
  const out = new Float32Array(n)
  for (let i = 0; i < n; i++) out[i] = dv.getFloat32(i * 4, true)
  return out
}

export function decodeFactors(buf: ArrayBuffer, width: number, height: number): Uint8Array {
  if (buf.byteLength !== width * height) throw new Error(`Risk factors: expected ${width * height} bytes, got ${buf.byteLength}`)
  return new Uint8Array(buf)
}

/** Fractional position in cell-center space (0 = center of the first column/row), or null outside the grid. */
export function cellPos(idx: RiskIndex, lon: number, lat: number): { x: number; y: number } | null {
  const [w, s, e, n] = idx.bounds
  if (lon < w || lon > e || lat < s || lat > n) return null
  return { x: ((lon - w) / (e - w)) * idx.width - 0.5, y: ((n - lat) / (n - s)) * idx.height - 0.5 }
}

/** Bilinear sample between cell centers. NaN neighbours are dropped; null when none are valid. */
export function sample(idx: RiskIndex, values: Float32Array, lon: number, lat: number): number | null {
  const p = cellPos(idx, lon, lat)
  if (!p) return null
  const x = Math.min(idx.width - 1, Math.max(0, p.x))
  const y = Math.min(idx.height - 1, Math.max(0, p.y))
  const x0 = Math.floor(x)
  const y0 = Math.floor(y)
  const x1 = Math.min(idx.width - 1, x0 + 1)
  const y1 = Math.min(idx.height - 1, y0 + 1)
  const fx = x - x0
  const fy = y - y0
  const pts: [number, number][] = [
    [values[y0 * idx.width + x0], (1 - fx) * (1 - fy)],
    [values[y0 * idx.width + x1], fx * (1 - fy)],
    [values[y1 * idx.width + x0], (1 - fx) * fy],
    [values[y1 * idx.width + x1], fx * fy],
  ]
  // The nearest cell must be valid, or the point is outside the study area.
  if (!Number.isFinite(values[Math.round(y) * idx.width + Math.round(x)])) return null
  let sum = 0
  let wsum = 0
  for (const [v, wt] of pts) {
    if (!Number.isFinite(v) || wt === 0) continue
    sum += v * wt
    wsum += wt
  }
  return wsum > 0 ? sum / wsum : null
}
