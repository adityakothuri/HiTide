import type { Access, Community, EvidenceState, Observation, Road, Task } from '../types'

/** Pure helpers that turn the evidence snapshot into what the inspections workspace shows. */

const MINUTE = 60_000

export function ageLabel(iso: string | null | undefined, now: number): string | null {
  if (!iso) return null
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return null
  const mins = Math.max(0, Math.round((now - t) / MINUTE))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m`
  const hours = Math.round(mins / 60)
  if (hours < 48) return `${hours}h`
  return `${Math.round(hours / 24)}d`
}

export function secondsAgo(iso: string | null | undefined, now: number): string {
  if (!iso) return 'never'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return 'unknown'
  const s = Math.max(0, Math.round((now - t) / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  return m < 60 ? `${m}m ago` : `${Math.round(m / 60)}h ago`
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return '--:--'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '--:--' : d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })
}

export function fullTime(iso: string | null | undefined): string {
  if (!iso) return 'Not supplied'
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? 'Invalid timestamp'
    : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
}

export const ACCESS_LABEL: Record<Access, string> = {
  open: 'Reported open',
  closed: 'Closed',
  restricted: 'Restricted',
  unknown: 'Unknown',
}

/** Observations about one road, plus context (warnings, gauges) its task cites. Newest first. */
export function roadEvidence(state: EvidenceState, road: Road, task?: Task): Observation[] {
  const cited = new Set([...road.evidence_ids, ...(task?.evidence_ids ?? [])])
  return state.observations
    .filter((o) => cited.has(o.id) || o.road_id === road.id)
    .sort((a, b) => (b.observed_at ?? '').localeCompare(a.observed_at ?? ''))
}

/** Latest direct observation of the road itself (not area context). */
export function latestDirect(state: EvidenceState, road: Road): Observation | undefined {
  return state.observations
    .filter((o) => o.road_id === road.id)
    .sort((a, b) => (b.observed_at ?? '').localeCompare(a.observed_at ?? ''))[0]
}

export type QueueTab = 'review' | 'assigned'

export function tasksFor(state: EvidenceState, tab: QueueTab): Task[] {
  const wanted = tab === 'review' ? ['queued', 'inconclusive'] : ['assigned']
  return state.tasks.filter((t) => wanted.includes(t.status)).sort((a, b) => b.priority - a.priority)
}

const HIGH_PRIORITY = 1000

export function isHighPriority(task: Task): boolean {
  return task.priority >= HIGH_PRIORITY || task.reasons.some((r) => /removes all modeled exits/i.test(r))
}

export function communityNames(state: EvidenceState, ids: string[]): Community[] {
  return ids.map((id) => state.communities.find((c) => c.id === id || c.name === id)).filter((c): c is Community => !!c)
}

const shortName = (name: string) => name.replace(/\s*\((synthetic|simulated)\)\s*$/i, '')

/** One-line reason for the queue: the consequence first, then the first stated reason. */
export function taskSummary(state: EvidenceState, task: Task): string {
  const communities = communityNames(state, task.affected_communities)
  const lastExit = communities.find((c) => c.remaining_exits === 1)
  if (lastExit) return `Only modeled exit · ${shortName(lastExit.name)}`
  return task.reasons[0] ?? 'Needs verification'
}

export type Chip = { label: string; tone: 'neutral' | 'closed' | 'open' | 'caution' | 'conflict' }

export function accessChip(road: Road): Chip {
  if (road.agreement === 'conflicting') return { label: 'Conflicting', tone: 'conflict' }
  const tone = road.access === 'closed' ? 'closed' : road.access === 'open' ? 'open' : road.access === 'restricted' ? 'caution' : 'neutral'
  return { label: road.access === 'open' ? 'Open' : ACCESS_LABEL[road.access], tone }
}

export function freshnessChip(road: Road): Chip | null {
  if (road.freshness === 'stale') return { label: 'Stale evidence', tone: 'caution' }
  if (road.freshness === 'missing') return { label: 'No direct evidence', tone: 'caution' }
  return null
}

export function guidance(road: Road): string {
  if (road.agreement === 'conflicting') return 'Sources disagree. Verify on site before relying on either report.'
  if (road.access === 'closed') return 'Closure reported. Confirm conditions before reopening access.'
  if (road.access === 'open' && road.freshness === 'current') return 'Recent evidence reports this road open. It is not certified safe.'
  return 'Verify this crossing before updating community access.'
}

export interface Summary {
  awaiting: number
  conflicting: number
  communitiesAffected: number
}

export function summary(state: EvidenceState): Summary {
  return {
    awaiting: state.tasks.filter((t) => t.status === 'queued' || t.status === 'inconclusive').length,
    conflicting: state.roads.filter((r) => r.agreement === 'conflicting').length,
    communitiesAffected: state.communities.filter((c) => !c.conservative_access).length,
  }
}

export interface WarningInfo {
  title: string
  source: string
  link: string | null
}

const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v.trim() : null)

/** The newest active hazard warning, if any. A warning is area context, never a road closure. */
export function activeWarning(state: EvidenceState): WarningInfo | null {
  const w = state.observations
    .filter((o) => o.kind === 'warning' || o.kind === 'alert')
    .sort((a, b) => (b.observed_at ?? '').localeCompare(a.observed_at ?? ''))[0]
  if (!w) return null
  const raw = w.raw
  const event = str(raw.event) ?? str(raw.headline) ?? str(raw.description) ?? 'Flood warning'
  const area = str(raw.areaDesc) ?? str(raw.area) ?? 'Kerr County'
  const link = [raw.url, raw.link, raw.web, raw.id].map(str).find((v) => v?.startsWith('https://')) ?? null
  const title = event.replace(/^synthetic\s+(active\s+)?/i, '').replace(/^./, (c) => c.toUpperCase())
  return { title: `${title} · ${area}`, source: sourceShort(w.source_id), link }
}

export function sourceShort(id: string): string {
  if (/nws/i.test(id)) return 'NWS'
  if (/usgs/i.test(id)) return 'USGS'
  if (/drivetexas|txdot|agency/i.test(id)) return 'Agency'
  if (/drone/i.test(id)) return 'Drone'
  if (/local|report|community/i.test(id)) return 'Community'
  return id.replaceAll('_', ' ')
}

/** Roads worth drawing: anything with evidence, a task, a non-unknown state, or a conflict. */
export function mappedRoads(state: EvidenceState): Road[] {
  const taskRoads = new Set(state.tasks.map((t) => t.road_id))
  return state.roads.filter(
    (r) => r.evidence_ids.length > 0 || taskRoads.has(r.id) || r.access !== 'unknown' || r.agreement === 'conflicting',
  )
}

export function midpoint(road: Road): [number, number] | null {
  const c = road.geometry?.coordinates
  if (!c?.length) return null
  const p = c[Math.floor(c.length / 2)]
  return [p[0], p[1]]
}
