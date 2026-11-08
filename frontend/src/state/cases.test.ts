import { describe, expect, it } from 'vitest'
import { caseSeverity, filterCases, sortCases, stateIndex, stepLabel, upsertCase } from './cases'
import { caseAt, makeCase } from './fixtures'

describe('sortCases', () => {
  it('sorts by urgency, highest first, without mutating', () => {
    const a = makeCase({ id: 'a', urgency: 0.4 })
    const b = makeCase({ id: 'b', urgency: 0.9 })
    const input = [a, b]
    expect(sortCases(input).map((c) => c.id)).toEqual(['b', 'a'])
    expect(input.map((c) => c.id)).toEqual(['a', 'b'])
  })
  it('puts resolved cases last regardless of urgency', () => {
    const r = makeCase({ id: 'r', urgency: 0.99, state: 'resolved' })
    const o = makeCase({ id: 'o', urgency: 0.2 })
    expect(sortCases([r, o]).map((c) => c.id)).toEqual(['o', 'r'])
  })
  it('breaks ties by the oldest case first', () => {
    const late = makeCase({ id: 'late', opened_at: '2026-11-08T03:00:00Z' })
    const early = makeCase({ id: 'early', opened_at: '2026-11-08T02:00:00Z' })
    expect(sortCases([late, early]).map((c) => c.id)).toEqual(['early', 'late'])
  })
})

describe('upsertCase', () => {
  it('adds a new case and keeps order', () => {
    const out = upsertCase([makeCase({ id: 'a', urgency: 0.5 })], makeCase({ id: 'b', urgency: 0.8 }))
    expect(out.map((c) => c.id)).toEqual(['b', 'a'])
  })
  it('replaces an existing case by id', () => {
    const out = upsertCase([caseAt('calling')], caseAt('drone_en_route'))
    expect(out).toHaveLength(1)
    expect(out[0].state).toBe('drone_en_route')
  })
})

describe('stateIndex', () => {
  it('follows the escalation order', () => {
    expect(stateIndex('monitoring')).toBeLessThan(stateIndex('calling'))
    expect(stateIndex('drone_en_route')).toBeLessThan(stateIndex('handed_to_responders'))
    expect(stateIndex('handed_to_responders')).toBeLessThan(stateIndex('resolved'))
  })
})

describe('caseSeverity', () => {
  it('is safe once resolved', () => {
    expect(caseSeverity(caseAt('resolved'))).toBe('safe')
  })
  it('is critical for high urgency or a responder flag', () => {
    expect(caseSeverity(makeCase({ urgency: 0.75, responder_flag: false }))).toBe('critical')
    expect(caseSeverity(makeCase({ urgency: 0.2, responder_flag: true }))).toBe('critical')
  })
  it('is caution otherwise', () => {
    expect(caseSeverity(makeCase({ urgency: 0.3, responder_flag: false }))).toBe('caution')
  })
})

describe('filterCases', () => {
  const cases = [
    makeCase({ id: 'crit', urgency: 0.9, state: 'drone_en_route' }),
    makeCase({ id: 'call', urgency: 0.3, responder_flag: false, state: 'calling' }),
    makeCase({ id: 'fam', urgency: 0.3, responder_flag: false, state: 'contacting_family' }),
    makeCase({ id: 'done', state: 'resolved' }),
  ]
  it('critical excludes resolved cases', () => {
    expect(filterCases(cases, 'critical').map((c) => c.id)).toEqual(['crit'])
  })
  it('contacting includes calling and family', () => {
    expect(filterCases(cases, 'contacting').map((c) => c.id)).toEqual(['call', 'fam'])
  })
  it('drone includes en route and verified', () => {
    expect(filterCases(cases, 'drone').map((c) => c.id)).toEqual(['crit'])
  })
  it('resolved is only resolved', () => {
    expect(filterCases(cases, 'resolved').map((c) => c.id)).toEqual(['done'])
  })
  it('all returns everything', () => {
    expect(filterCases(cases, 'all')).toHaveLength(4)
  })
})

describe('stepLabel', () => {
  it('reads as a plain current step', () => {
    expect(stepLabel('calling')).toBe('Calling driver')
    expect(stepLabel('contacting_family')).toBe('Contacting family')
    expect(stepLabel('drone_en_route')).toBe('Drone en route')
    expect(stepLabel('handed_to_responders')).toBe('With responders')
  })
})
