import type { Area, AreaStatus, DangerLevel, FleetDrone, Person, PointStatus } from './types'

/** One colour meaning across map and panels: red = in danger now, amber = at risk, grey = watched. */
export type Tone = 'critical' | 'warning' | 'muted'

const LEVEL_RANK: Record<DangerLevel, number> = { none: 0, watch: 1, warning: 2, danger: 3, critical: 4 }
const AREA_RANK: Record<AreaStatus, number> = { ok: 0, at_risk: 1, partially_cut_off: 2, cut_off: 3 }

export function personTone(level: DangerLevel): Tone {
  return level === 'critical' || level === 'danger' ? 'critical' : level === 'warning' ? 'warning' : 'muted'
}

export function areaTone(status: AreaStatus): Tone {
  return status === 'cut_off' ? 'critical' : status === 'ok' ? 'muted' : 'warning'
}

export function pointTone(status: PointStatus): Tone {
  return status === 'confirmed_flooded' ? 'critical' : status === 'likely_flooded' ? 'warning' : 'muted'
}

/** They told us they need help (text, poll or the HiTide call): always listed, always first. */
export function needsHelp(p: Person): boolean {
  return p.response?.need_help === true
}

const CALL_ENTRY = /^(assistant call|call\b)|voice:/i

/** True when the outreach timeline shows a call or the HiTide assistant call. */
export function hadCall(p: Person): boolean {
  return (p.response?.timeline ?? []).some((e) => CALL_ENTRY.test(e.what))
}

/** The latest "assistant call: <summary>" text, if the assistant call produced one. */
export function lastCallSummary(p: Person): string | null {
  const hit = [...(p.response?.timeline ?? [])].reverse().find((e) => e.what.startsWith('assistant call: '))
  return hit ? hit.what.slice('assistant call: '.length).trim() || null : null
}

/** When they asked for help (the HELP timeline entry), in epoch seconds. */
export function helpAt(p: Person): number | null {
  const hit = [...(p.response?.timeline ?? [])].reverse().find((e) => e.what.startsWith('HELP from '))
  return hit ? hit.t : null
}

/** Asked for help first; then most urgent; within a level, a car stopped in water first; then by name. */
export function sortPeople(people: readonly Person[], names: Readonly<Record<string, string>>): Person[] {
  const name = (p: Person) => names[p.user_id] ?? p.user_id
  return [...people].sort(
    (a, b) =>
      Number(needsHelp(b)) - Number(needsHelp(a)) ||
      LEVEL_RANK[b.level] - LEVEL_RANK[a.level] ||
      Number(b.stopped_in_water) - Number(a.stopped_in_water) ||
      name(a).localeCompare(name(b)),
  )
}

export function peopleSummary(people: readonly Person[]): { critical: number; danger: number; warning: number } {
  const out = { critical: 0, danger: 0, warning: 0 }
  for (const p of people) if (p.level === 'critical' || p.level === 'danger' || p.level === 'warning') out[p.level] += 1
  return out
}

/** Areas that are not ok: cut off first, then by households. */
export function areasAtRisk(areas: readonly Area[]): Area[] {
  return areas.filter((a) => a.status !== 'ok').sort((a, b) => AREA_RANK[b.status] - AREA_RANK[a.status] || b.households - a.households)
}

const pointName = (id: string | null, names: Readonly<Record<string, string>>) => (id && names[id]) || 'a crossing'

export function droneLabel(d: FleetDrone, names: Readonly<Record<string, string>>): string {
  if (d.status === 'flying') return `Flying to ${pointName(d.target, names)}`
  if (d.status === 'snapshot') return `Checking ${pointName(d.target, names)}`
  if (d.status === 'returning') return 'Returning to station'
  return 'At station'
}

/** Stops still ahead after the current target, as names. */
export function nextStops(d: FleetDrone, names: Readonly<Record<string, string>>, n: number): string[] {
  const i = d.target ? d.tour.indexOf(d.target) : -1
  return d.tour.slice(i + 1, i + 1 + n).map((id) => pointName(id, names))
}

/** Point id -> the drone that will check it next (first tour that lists it). */
export function droneOfPoint(drones: readonly FleetDrone[]): Map<string, string> {
  const out = new Map<string, string>()
  for (const d of drones) for (const id of d.tour) if (!out.has(id)) out.set(id, d.id)
  return out
}

/** "drone-hunt" -> "Hunt drone". Named by home station, which stays fixed while the drone recharges elsewhere. */
export function droneName(d: Pick<FleetDrone, 'id'>): string {
  const base = d.id.replace(/^drone-/, '').replace(/[-_]+/g, ' ')
  return `${base.charAt(0).toUpperCase()}${base.slice(1)} drone`
}

/** "Hunt Volunteer Fire Department" -> "Hunt". */
export function stationShort(station: string): string {
  return station.replace(/\s+(Volunteer|Central)?\s*Fire (Department|Station).*$/i, '').trim() || station
}
