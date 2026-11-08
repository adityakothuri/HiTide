import { BANDS, type Band } from './bands'

export interface RiskTicks {
  ticks: { pos: number; label: string }[]
  bands: { pos: number; label: Band }[]
}

/** Colorbar ticks for the risk index: numbers at the band edges, band names at their midpoints (0..1, bottom up). */
export function riskTicks(): RiskTicks {
  return {
    ticks: [0, 25, 50, 75, 100].map((v) => ({ pos: v / 100, label: String(v) })),
    bands: BANDS.map((b) => ({ pos: (b.from + b.to) / 200, label: b.label })),
  }
}
