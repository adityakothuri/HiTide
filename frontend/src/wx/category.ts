import type { CategoryStages, FloodCategory } from './types'

export const CATEGORY_LABEL: Record<FloodCategory, string> = {
  below: 'Below action stage',
  action: 'Action stage',
  minor: 'Minor flooding',
  moderate: 'Moderate flooding',
  major: 'Major flooding',
  none: 'No NWS flood categories',
}

/** NWS flood category for a stage. A stage at a threshold is in that category. */
export function categoryOf(stageFt: number | null, cats: CategoryStages | null): FloodCategory {
  if (!cats || stageFt == null) return 'none'
  if (stageFt >= cats.major) return 'major'
  if (stageFt >= cats.moderate) return 'moderate'
  if (stageFt >= cats.minor) return 'minor'
  if (stageFt >= cats.action) return 'action'
  return 'below'
}

/** Linear interpolation in a time series; null outside it or across a gap longer than maxGapMs. */
export function sampleSeries(series: readonly (readonly [number, number])[], t: number, maxGapMs: number): number | null {
  if (series.length === 0 || t < series[0][0] || t > series[series.length - 1][0]) return null
  const hi = series.findIndex(([ts]) => ts >= t)
  if (hi < 0) return null
  if (series[hi][0] === t) return series[hi][1]
  const [t0, v0] = series[hi - 1]
  const [t1, v1] = series[hi]
  if (t1 - t0 > maxGapMs) return null
  return v0 + ((v1 - v0) * (t - t0)) / (t1 - t0)
}
