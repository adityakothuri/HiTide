import { band, type Band } from './bands'
import { cellPos, type RiskIndex } from './grid'

export interface Readout {
  value: number
  band: Band
  /** Top two contributing factors for this cell, most important first. */
  factors: string[]
}

const NO_FACTOR = 255

/** Hover readout for the nearest cell: value, band and the two factors driving it. */
export function readout(idx: RiskIndex, values: Float32Array, factors: Uint8Array | null, lon: number, lat: number): Readout | null {
  const p = cellPos(idx, lon, lat)
  if (!p) return null
  const col = Math.min(idx.width - 1, Math.max(0, Math.round(p.x)))
  const row = Math.min(idx.height - 1, Math.max(0, Math.round(p.y)))
  const i = row * idx.width + col
  const v = values[i]
  if (!Number.isFinite(v)) return null
  const names: string[] = []
  const byte = factors?.[i] ?? NO_FACTOR
  if (byte !== NO_FACTOR) {
    for (const k of [byte >> 4, byte & 0x0f]) {
      const name = idx.factors[k]
      if (name && !names.includes(name)) names.push(name)
    }
  }
  return { value: Math.round(v), band: band(v), factors: names }
}
