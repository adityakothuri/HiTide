const TZ = 'America/Chicago'
const MIN_MS = 60_000
const FEET_PER_M = 3.28084
const M_PER_MILE = 1609.34
const FEET_CUTOFF_M = M_PER_MILE / 10

const clockFmt = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone: TZ })

/** "8:42 PM" in Kerrville time. */
export function formatClock(iso: string): string {
  const t = Date.parse(iso)
  return Number.isNaN(t) ? '—' : clockFmt.format(t)
}

/** "Just now", "4 min ago", "1 hr 5 min ago". */
export function formatRelative(iso: string, nowMs: number): string {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return '—'
  const mins = Math.floor((nowMs - t) / MIN_MS)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins} min ago`
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return m === 0 ? `${h} hr ago` : `${h} hr ${m} min ago`
}

/** Water depth in plain words: "14 in", "3 ft 4 in". */
export function formatDepth(inches: number): string {
  if (inches < 1) return 'Less than 1 in'
  const whole = Math.round(inches)
  if (whole < 36) return `${whole} in`
  const ft = Math.floor(whole / 12)
  const rest = whole % 12
  return rest === 0 ? `${ft} ft` : `${ft} ft ${rest} in`
}

/** "500 ft" under a tenth of a mile, else "2.9 miles". */
export function formatDistance(meters: number): string {
  if (meters < FEET_CUTOFF_M) {
    const ft = Math.max(50, Math.round((meters * FEET_PER_M) / 50) * 50)
    return `${ft} ft`
  }
  const miles = Math.round((meters / M_PER_MILE) * 10) / 10
  return miles === 1 ? '1 mile' : `${miles} miles`
}

const BANDS: [number, string][] = [
  [18, 'Under 18'],
  [25, '18–24'],
  [35, '25–34'],
  [50, '35–49'],
  [65, '50–64'],
  [75, '65–74'],
]

export function ageBand(age: number): string {
  for (const [limit, label] of BANDS) if (age < limit) return label
  return '75+'
}

export function firstName(name: string): string {
  return name.trim().split(/\s+/)[0] || 'Unknown driver'
}

/** "$54,000" */
export function formatUsd(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}
