/** Relative bands of the flood risk index. Labels, not depths. */
export type Band = 'Low' | 'Moderate' | 'High' | 'Severe'

export const BANDS: readonly { label: Band; from: number; to: number }[] = [
  { label: 'Low', from: 0, to: 25 },
  { label: 'Moderate', from: 25, to: 50 },
  { label: 'High', from: 50, to: 75 },
  { label: 'Severe', from: 75, to: 100 },
]

export function band(index: number): Band {
  if (index >= 75) return 'Severe'
  if (index >= 50) return 'High'
  if (index >= 25) return 'Moderate'
  return 'Low'
}
