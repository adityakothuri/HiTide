export const STALE_AFTER_MS = 5 * 60_000

export function isStale(iso: string | null | undefined, nowMs: number, thresholdMs = STALE_AFTER_MS): boolean {
  if (!iso) return true
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return true
  return nowMs - t > thresholdMs
}
