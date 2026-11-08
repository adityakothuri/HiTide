import type { Case, CaseState, DroneState, WsEvent } from '../data/types'

export function makeCase(over: Partial<Case> = {}): Case {
  return {
    id: 'case-001',
    driver_id: 'demo-d',
    driver_name: 'Margaret Hale',
    state: 'calling',
    urgency: 0.9,
    urgency_reasons: ['stopped in floodwater', 'age 78'],
    responder_flag: true,
    location: { lat: 30.036, lon: -99.136 },
    depth_in: 20,
    opened_at: '2026-11-08T02:42:00Z',
    timeline: [],
    vision: null,
    responder_view: { location: { lat: 30.036, lon: -99.136 }, people_count: null, water_depth_in: 20 },
    ...over,
  }
}

export function caseAt(state: CaseState, over: Partial<Case> = {}): Case {
  return makeCase({ state, ...over })
}

export function makeDrone(over: Partial<DroneState> = {}): DroneState {
  return { id: 'drone-1', case_id: 'case-001', lat: 30.05, lon: -99.14, eta_s: 120, status: 'en_route', ...over }
}

let seq = 100
export function ev<T extends WsEvent['type']>(type: T, payload: Extract<WsEvent, { type: T }>['payload'], s?: number): WsEvent {
  seq += 1
  return { type, seq: s ?? seq, ts: '2026-11-08T02:45:00Z', payload } as WsEvent
}
