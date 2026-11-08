import type {
  Alert, Case, Counters, DemoStep, DriverPublic, DroneState, OutreachEvent, Reroute, SegmentState, TurnAround, WsEvent,
} from '../data/types'
import { upsertCase } from './cases'

export const OUTREACH_CAP = 200
export const TRAIL_CAP = 500

export type DroneWithTrail = DroneState & { trail: [number, number][] }

export interface AppState {
  lastSeq: number
  lastEventAt: string | null
  t_sim_s: number
  river_wse_m: number
  alert: Alert | null
  segments: Record<string, SegmentState>
  drivers: Record<string, DriverPublic>
  cases: Case[]
  drones: Record<string, DroneWithTrail>
  counters: Counters
  outreach: OutreachEvent[]
  pretrip: Record<string, OutreachEvent>
  turnArounds: Record<string, TurnAround>
  reroutes: Record<string, Reroute>
  demoStep: DemoStep | null
  focusDriverId: string | null
  newestCaseId: string | null
  /** Bumps when the sim resets (snapshot with earlier sim time). UI-only state keys off this. */
  epoch: number
}

export const initialState: AppState = {
  lastSeq: -1,
  lastEventAt: null,
  t_sim_s: 0,
  river_wse_m: 0,
  alert: null,
  segments: {},
  drivers: {},
  cases: [],
  drones: {},
  counters: { drivers_warned: 0, drivers_rerouted: 0, cars_stopped_in_water: 0, people_verified: 0, est_claims_avoided_usd: 0 },
  outreach: [],
  pretrip: {},
  turnArounds: {},
  reroutes: {},
  demoStep: null,
  focusDriverId: null,
  newestCaseId: null,
  epoch: 0,
}

function isDemoDriver(s: AppState, id: string): boolean {
  return s.drivers[id]?.is_demo ?? id.startsWith('demo-')
}

function focus(s: AppState, driverId: string): string | null {
  return isDemoDriver(s, driverId) ? driverId : s.focusDriverId
}

function byKey<T>(items: readonly T[], key: (t: T) => string): Record<string, T> {
  return Object.fromEntries(items.map((i) => [key(i), i]))
}

function withTrail(prev: DroneWithTrail | undefined, d: DroneState): DroneWithTrail {
  const point: [number, number] = [d.lon, d.lat]
  const trail = prev?.trail ?? []
  const last = trail[trail.length - 1]
  const same = last && last[0] === point[0] && last[1] === point[1]
  const next = same ? trail : [...trail, point].slice(-TRAIL_CAP)
  return { ...d, trail: next }
}

function applySegments(prev: Record<string, SegmentState>, diff: readonly SegmentState[]): Record<string, SegmentState> {
  const next = { ...prev }
  for (const seg of diff) {
    if (seg.status === 'open') delete next[seg.edge_id]
    else next[seg.edge_id] = seg
  }
  return next
}

/**
 * Pure reducer for every WS event. Snapshot replaces everything; other events are ignored if their
 * seq is stale. Local, client-side events use seq -1 and skip the check.
 */
export function reduceEvent(state: AppState, event: WsEvent): AppState {
  if (event.type === 'snapshot') {
    const p = event.payload
    // A reconnect re-sends the snapshot: keep driver-side history. Earlier sim time means a reset.
    const isReset = p.t_sim_s < state.t_sim_s
    const history = isReset ? initialState : state
    return {
      ...history,
      epoch: isReset ? state.epoch + 1 : state.epoch,
      newestCaseId: null,
      lastSeq: event.seq,
      lastEventAt: event.ts,
      t_sim_s: p.t_sim_s,
      river_wse_m: p.river_wse_m,
      alert: p.alert,
      segments: applySegments({}, p.segments),
      drivers: byKey(p.drivers, (d) => d.id),
      cases: upsertMany(p.cases),
      drones: Object.fromEntries(p.drones.map((d) => [d.id, withTrail(history.drones[d.id], d)])),
      counters: p.counters,
    }
  }
  const isLocal = event.seq < 0
  if (!isLocal && event.seq <= state.lastSeq) return state
  const s: AppState = { ...state, lastSeq: isLocal ? state.lastSeq : event.seq, lastEventAt: event.ts }

  switch (event.type) {
    case 'segments.update':
      return { ...s, t_sim_s: event.payload.t_sim_s, river_wse_m: event.payload.river_wse_m, segments: applySegments(s.segments, event.payload.segments) }
    case 'drivers.update':
      return { ...s, drivers: { ...s.drivers, ...byKey(event.payload.drivers, (d) => d.id) } }
    case 'alert':
      return { ...s, alert: event.payload }
    case 'outreach': {
      const o = event.payload
      const outreach = [...s.outreach, o].slice(-OUTREACH_CAP)
      const isPretrip = o.recipient === 'driver' && o.channel === 'text' && !o.case_id
      if (!isPretrip) return { ...s, outreach }
      return { ...s, outreach, pretrip: { ...s.pretrip, [o.driver_id]: o }, focusDriverId: focus(s, o.driver_id) }
    }
    case 'turn_around':
      return { ...s, turnArounds: { ...s.turnArounds, [event.payload.driver_id]: event.payload }, focusDriverId: focus(s, event.payload.driver_id) }
    case 'reroute':
      return { ...s, reroutes: { ...s.reroutes, [event.payload.driver_id]: event.payload } }
    case 'case.update': {
      const c = event.payload
      const isNew = !s.cases.some((x) => x.id === c.id)
      return { ...s, cases: upsertCase(s.cases, c), newestCaseId: isNew ? c.id : s.newestCaseId, focusDriverId: focus(s, c.driver_id) }
    }
    case 'drone.update':
      return { ...s, drones: { ...s.drones, [event.payload.id]: withTrail(s.drones[event.payload.id], event.payload) } }
    case 'counters':
      return { ...s, counters: event.payload }
    case 'demo.step':
      return { ...s, demoStep: event.payload }
    default:
      return s
  }
}

function upsertMany(cases: readonly Case[]): Case[] {
  return cases.reduce<Case[]>((acc, c) => upsertCase(acc, c), [])
}
