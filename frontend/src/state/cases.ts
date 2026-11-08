import type { Case, CaseState } from '../data/types'

export const CASE_STATES: readonly CaseState[] = [
  'monitoring',
  'calling',
  'contacting_family',
  'drone_en_route',
  'verified',
  'handed_to_responders',
  'resolved',
]

export const CRITICAL_URGENCY = 0.7

export type Severity = 'critical' | 'caution' | 'safe'
export type CaseFilter = 'all' | 'critical' | 'contacting' | 'drone' | 'resolved'

export function stateIndex(state: CaseState): number {
  return CASE_STATES.indexOf(state)
}

export function caseSeverity(c: Case): Severity {
  if (c.state === 'resolved') return 'safe'
  if (c.responder_flag || c.urgency >= CRITICAL_URGENCY) return 'critical'
  return 'caution'
}

function compare(a: Case, b: Case): number {
  const ra = a.state === 'resolved' ? 1 : 0
  const rb = b.state === 'resolved' ? 1 : 0
  if (ra !== rb) return ra - rb
  if (a.urgency !== b.urgency) return b.urgency - a.urgency
  return Date.parse(a.opened_at) - Date.parse(b.opened_at)
}

export function sortCases(cases: readonly Case[]): Case[] {
  return [...cases].sort(compare)
}

export function upsertCase(cases: readonly Case[], next: Case): Case[] {
  const rest = cases.filter((c) => c.id !== next.id)
  return sortCases([...rest, next])
}

const FILTERS: Record<Exclude<CaseFilter, 'all'>, (c: Case) => boolean> = {
  critical: (c) => caseSeverity(c) === 'critical',
  contacting: (c) => c.state === 'calling' || c.state === 'contacting_family',
  drone: (c) => c.state === 'drone_en_route' || c.state === 'verified',
  resolved: (c) => c.state === 'resolved',
}

export function filterCases(cases: readonly Case[], filter: CaseFilter): Case[] {
  return filter === 'all' ? [...cases] : cases.filter(FILTERS[filter])
}

const STEP_LABELS: Record<CaseState, string> = {
  monitoring: 'Checking on driver',
  calling: 'Calling driver',
  contacting_family: 'Contacting family',
  drone_en_route: 'Drone en route',
  verified: 'Drone on scene',
  handed_to_responders: 'With responders',
  resolved: 'Resolved',
}

export function stepLabel(state: CaseState): string {
  return STEP_LABELS[state]
}
