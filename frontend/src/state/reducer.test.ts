import { describe, expect, it } from 'vitest'
import type { StateSnapshot } from '../data/types'
import { initialState, reduceEvent } from './reducer'
import { caseAt, ev, makeDrone } from './fixtures'

const snap: StateSnapshot = {
  t_sim_s: 0,
  river_wse_m: 490,
  alert: null,
  segments: [{ edge_id: 's1', depth_in: 8, status: 'closed' }],
  drivers: [{ id: 'demo-d', name: 'Margaret Hale', lat: 30, lon: -99, heading_deg: 0, situation: 'driving', is_demo: true, urgency: 0 }],
  cases: [],
  drones: [],
  counters: { drivers_warned: 0, drivers_rerouted: 0, cars_stopped_in_water: 0, people_verified: 0, est_claims_avoided_usd: 0 },
}

describe('reduceEvent', () => {
  it('replaces all state on snapshot', () => {
    const dirty = reduceEvent(initialState, ev('case.update', caseAt('calling'), 1))
    const s = reduceEvent(dirty, ev('snapshot', snap, 5))
    expect(s.cases).toEqual([])
    expect(s.segments.s1.status).toBe('closed')
    expect(s.drivers['demo-d'].name).toBe('Margaret Hale')
    expect(s.lastSeq).toBe(5)
  })

  it('keeps driver-side history on a reconnect snapshot (sim time did not go back)', () => {
    let s = reduceEvent(initialState, ev('snapshot', { ...snap, t_sim_s: 100 }, 1))
    s = reduceEvent(s, ev('turn_around', { driver_id: 'demo-b', message: 'm', hazard_edge_id: 'e', hazard_depth_in: 14, distance_m: 180 }, 2))
    const epoch = s.epoch
    s = reduceEvent(s, ev('snapshot', { ...snap, t_sim_s: 160 }, 3))
    expect(s.turnArounds['demo-b']).toBeDefined()
    expect(s.focusDriverId).toBe('demo-b')
    expect(s.epoch).toBe(epoch)
  })

  it('clears history and bumps the epoch when the sim resets', () => {
    let s = reduceEvent(initialState, ev('snapshot', { ...snap, t_sim_s: 100 }, 1))
    s = reduceEvent(s, ev('turn_around', { driver_id: 'demo-b', message: 'm', hazard_edge_id: 'e', hazard_depth_in: 14, distance_m: 180 }, 2))
    const epoch = s.epoch
    s = reduceEvent(s, ev('snapshot', { ...snap, t_sim_s: 0 }, 3))
    expect(s.turnArounds).toEqual({})
    expect(s.focusDriverId).toBeNull()
    expect(s.epoch).toBe(epoch + 1)
  })

  it('ignores a duplicate or older seq', () => {
    const s1 = reduceEvent(initialState, ev('counters', { ...snap.counters, drivers_warned: 3 }, 10))
    const s2 = reduceEvent(s1, ev('counters', { ...snap.counters, drivers_warned: 1 }, 9))
    expect(s2.counters.drivers_warned).toBe(3)
  })

  it('applies local events (seq -1) without moving lastSeq', () => {
    const s1 = reduceEvent(initialState, ev('counters', snap.counters, 50))
    const s2 = reduceEvent(s1, ev('case.update', caseAt('calling'), -1))
    expect(s2.cases).toHaveLength(1)
    expect(s2.lastSeq).toBe(50)
    const s3 = reduceEvent(s2, ev('counters', { ...snap.counters, drivers_warned: 7 }, 51))
    expect(s3.counters.drivers_warned).toBe(7)
  })

  it('accepts a snapshot with a lower seq (backend restarted)', () => {
    const s1 = reduceEvent(initialState, ev('counters', snap.counters, 50))
    const s2 = reduceEvent(s1, ev('snapshot', snap, 1))
    expect(s2.lastSeq).toBe(1)
  })

  it('merges segment diffs and drops segments that reopen', () => {
    const s1 = reduceEvent(initialState, ev('snapshot', snap, 1))
    const s2 = reduceEvent(s1, ev('segments.update', { t_sim_s: 60, river_wse_m: 491, segments: [
      { edge_id: 's1', depth_in: 1, status: 'open' },
      { edge_id: 's2', depth_in: 30, status: 'boat' },
    ] }, 2))
    expect(s2.segments.s1).toBeUndefined()
    expect(s2.segments.s2.status).toBe('boat')
    expect(s2.t_sim_s).toBe(60)
  })

  it('records a pre-trip text for a driver and focuses demo drivers', () => {
    const s = reduceEvent(initialState, ev('outreach', {
      id: 'o1', ts: '2026-11-08T02:40:00Z', driver_id: 'demo-a', recipient: 'driver', channel: 'text',
      body: 'Flash flood warning', mode: 'mock', status: 'sent', case_id: null,
    }))
    expect(s.pretrip['demo-a'].id).toBe('o1')
    expect(s.focusDriverId).toBe('demo-a')
    expect(s.outreach).toHaveLength(1)
  })

  it('does not move focus for background drivers', () => {
    const s = reduceEvent(initialState, ev('outreach', {
      id: 'o2', ts: '2026-11-08T02:40:00Z', driver_id: 'd-007', recipient: 'driver', channel: 'text',
      body: 'x', mode: 'mock', status: 'sent', case_id: null,
    }))
    expect(s.focusDriverId).toBeNull()
    expect(s.pretrip['d-007']).toBeDefined()
  })

  it('upserts cases sorted and marks a brand-new case', () => {
    const s1 = reduceEvent(initialState, ev('case.update', caseAt('monitoring')))
    expect(s1.newestCaseId).toBe('case-001')
    expect(s1.focusDriverId).toBe('demo-d')
    const s2 = reduceEvent({ ...s1, newestCaseId: null }, ev('case.update', caseAt('calling')))
    expect(s2.cases[0].state).toBe('calling')
    expect(s2.newestCaseId).toBeNull()
  })

  it('tracks a drone trail without duplicate points', () => {
    const a = makeDrone({ lat: 30.05, lon: -99.14 })
    const b = makeDrone({ lat: 30.04, lon: -99.13, eta_s: 60 })
    let s = reduceEvent(initialState, ev('drone.update', a))
    s = reduceEvent(s, ev('drone.update', a))
    s = reduceEvent(s, ev('drone.update', b))
    expect(s.drones['drone-1'].trail).toEqual([[-99.14, 30.05], [-99.13, 30.04]])
    expect(s.drones['drone-1'].eta_s).toBe(60)
  })

  it('stores turn-around and reroute per driver', () => {
    let s = reduceEvent(initialState, ev('turn_around', { driver_id: 'demo-b', message: 'Flooded road ahead. Turn around.', hazard_edge_id: 'e', hazard_depth_in: 14, distance_m: 180 }))
    s = reduceEvent(s, ev('reroute', { driver_id: 'demo-b', reason: 'flood', route: { type: 'LineString', coordinates: [[0, 0], [1, 1]] }, blocked_edge_ids: ['e'], distance_m: 5000 }))
    expect(s.turnArounds['demo-b'].hazard_depth_in).toBe(14)
    expect(s.reroutes['demo-b'].distance_m).toBe(5000)
    expect(s.focusDriverId).toBe('demo-b')
  })

  it('caps the outreach log', () => {
    let s = initialState
    for (let i = 0; i < 260; i += 1) {
      s = reduceEvent(s, ev('outreach', { id: `o${i}`, ts: 'x', driver_id: 'd-1', recipient: 'driver', channel: 'text', body: '', mode: 'mock', status: 'sent', case_id: 'c' }))
    }
    expect(s.outreach.length).toBe(200)
    expect(s.outreach[199].id).toBe('o259')
  })
})
