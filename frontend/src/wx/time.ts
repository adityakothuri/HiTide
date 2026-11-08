/** Times on the ops console are local to Kerr County (CDT in July). */
const TZ = 'America/Chicago'

const clock = new Intl.DateTimeFormat('en-US', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
const day = new Intl.DateTimeFormat('en-US', { timeZone: TZ, weekday: 'short', month: 'short', day: 'numeric' })
const zone = new Intl.DateTimeFormat('en-US', { timeZone: TZ, timeZoneName: 'short' })

export function wxClock(ms: number): string {
  return clock.format(ms)
}

export function wxDay(ms: number): string {
  return day.format(ms)
}

export function wxZone(ms: number): string {
  return zone.formatToParts(ms).find((p) => p.type === 'timeZoneName')?.value ?? ''
}
