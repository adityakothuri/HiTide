import { describe, expect, it } from 'vitest'
import { areaTone, areasAtRisk, droneLabel, droneName, droneOfPoint, nextStops, peopleSummary, personTone, pointTone, sortPeople } from './derive'
import type { Area, FleetDrone, Person } from './types'

const person = (user_id: string, level: Person['level'], stopped = false): Person => ({ user_id, level, reasons: [`r-${user_id}`], stopped_in_water: stopped, location: {} })
const area = (id: string, status: Area['status'], households: number): Area => ({
  id, name: id, kind: 'homes', town: 'Hunt', lon: 0, lat: 0, households, status, instruction: 'none', rescue: null, unavoidable_points: [], reasons: [],
})
const drone = (id: string, over: Partial<FleetDrone> = {}): FleetDrone => ({
  id, station: 'Hunt Volunteer Fire Department', lat: 0, lon: 0, status: 'idle', target: null, eta_s: 0, battery_pct: 100, tour: [], path: [], km_flown: 0, ...over,
})

describe('people', () => {
  it('puts critical first, then stopped-in-water within a level, then name', () => {
    const out = sortPeople([person('b', 'warning'), person('a', 'critical'), person('c', 'danger'), person('d', 'danger', true)], { d: 'Zed', c: 'Amy' })
    expect(out.map((p) => p.user_id)).toEqual(['a', 'd', 'c', 'b'])
  })

  it('puts anyone who asked for help first, ahead of higher levels', () => {
    const helper: Person = { ...person('w', 'warning'), response: { awaiting_reply: false, called: true, call_unanswered: false, family_contacted: false, responders_flagged: true, case_open: true, need_help: true, safe_until: null, timeline: [] } }
    const out = sortPeople([person('a', 'critical'), helper, person('d', 'danger', true)], {})
    expect(out.map((p) => p.user_id)).toEqual(['w', 'a', 'd'])
  })

  it('counts each level', () => {
    expect(peopleSummary([person('a', 'critical'), person('b', 'danger'), person('c', 'danger'), person('d', 'warning')])).toEqual({ critical: 1, danger: 2, warning: 1 })
  })

  it('maps levels to the shared tones', () => {
    expect(personTone('critical')).toBe('critical')
    expect(personTone('danger')).toBe('critical')
    expect(personTone('warning')).toBe('warning')
    expect(personTone('watch')).toBe('muted')
  })
})

describe('areas', () => {
  it('keeps only areas that are not ok, worst status then most households first', () => {
    const out = areasAtRisk([area('ok', 'ok', 500), area('r1', 'at_risk', 10), area('c1', 'cut_off', 5), area('c2', 'cut_off', 40), area('p', 'partially_cut_off', 3)])
    expect(out.map((a) => a.id)).toEqual(['c2', 'c1', 'p', 'r1'])
  })

  it('maps status to tones', () => {
    expect(areaTone('cut_off')).toBe('critical')
    expect(areaTone('partially_cut_off')).toBe('warning')
    expect(areaTone('at_risk')).toBe('warning')
    expect(areaTone('ok')).toBe('muted')
  })
})

describe('points', () => {
  it('only flooded points get a colour', () => {
    expect(pointTone('confirmed_flooded')).toBe('critical')
    expect(pointTone('likely_flooded')).toBe('warning')
    expect(pointTone('unknown')).toBe('muted')
    expect(pointTone('open')).toBe('muted')
  })
})

describe('drones', () => {
  const names = { a: 'Bridge A', b: 'Crossing B', c: 'Low spot C' }

  it('describes what each drone is doing in words', () => {
    expect(droneLabel(drone('d', { status: 'flying', target: 'a' }), names)).toBe('Flying to Bridge A')
    expect(droneLabel(drone('d', { status: 'snapshot', target: 'b' }), names)).toBe('Checking Crossing B')
    expect(droneLabel(drone('d', { status: 'returning' }), names)).toBe('Returning to station')
    expect(droneLabel(drone('d'), names)).toBe('At station')
    expect(droneLabel(drone('d', { status: 'flying', target: 'zz' }), names)).toBe('Flying to a crossing')
  })

  it('lists the next stops after the current target', () => {
    expect(nextStops(drone('d', { target: 'a', tour: ['a', 'b', 'c'] }), names, 2)).toEqual(['Crossing B', 'Low spot C'])
    expect(nextStops(drone('d', { target: null, tour: ['a', 'b'] }), names, 5)).toEqual(['Bridge A', 'Crossing B'])
  })

  it('names a drone by its home, not the station it is recharging at', () => {
    expect(droneName(drone('drone-hunt', { station: 'Ingram Volunteer Fire Department' }))).toBe('Hunt drone')
  })

  it('assigns each point to the first drone whose tour includes it', () => {
    const map = droneOfPoint([drone('d1', { tour: ['a', 'b'] }), drone('d2', { tour: ['b', 'c'] })])
    expect(map.get('a')).toBe('d1')
    expect(map.get('b')).toBe('d1')
    expect(map.get('c')).toBe('d2')
  })
})
