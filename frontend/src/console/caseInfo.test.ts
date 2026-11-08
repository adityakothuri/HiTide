import { describe, expect, it } from 'vitest'
import { makeCase } from '../state/fixtures'
import { caseAgeBand, riskSummary, timelineRows } from './caseInfo'

describe('caseAgeBand', () => {
  it('uses the coarse band from urgency reasons for non-demo drivers', () => {
    const c = makeCase({ driver_id: 'd-001', urgency_reasons: ['night', 'older driver (65+)'] })
    expect(caseAgeBand(c)).toBe('65+')
  })
  it('uses the persona age for demo drivers', () => {
    expect(caseAgeBand(makeCase({ driver_id: 'demo-d' }))).toBe('75+')
  })
  it('returns null when nothing is known', () => {
    expect(caseAgeBand(makeCase({ driver_id: 'd-002', urgency_reasons: ['night'] }))).toBeNull()
  })
})

describe('timelineRows', () => {
  it('lifts mock markers into a simulated flag', () => {
    const c = makeCase({
      timeline: [
        { ts: '2026-11-08T02:52:39Z', t_case_s: 12, kind: 'outreach', text: 'Text + call to emergency contact (mock, sent)' },
        { ts: '2026-11-08T02:52:39Z', t_case_s: 12, kind: 'state', text: 'Contacting family' },
      ],
    })
    const rows = timelineRows(c)
    expect(rows[0]).toMatchObject({ text: 'Text + call to emergency contact', simulated: true })
    expect(rows[1]).toMatchObject({ text: 'Contacting family', simulated: false })
  })
  it('cleans a trailing colon left by the marker', () => {
    const c = makeCase({ timeline: [{ ts: '2026-11-08T02:52:27Z', t_case_s: 0, kind: 'outreach', text: 'Voice to driver (mock): voice sent' }] })
    expect(timelineRows(c)[0].text).toBe('Voice to driver: voice sent')
  })
})

describe('riskSummary', () => {
  it('turns the backend reasons into one plain sentence', () => {
    expect(
      riskSummary(['stopped in floodwater', '21 in of water', 'water rising 7.9 in/min', 'night', 'older driver (65+)', 'low-clearance vehicle']),
    ).toBe('Stopped in 21 in of rising water at night. Older driver (65+), low-clearance vehicle.')
  })
  it('handles a short list', () => {
    expect(riskSummary(['stopped in floodwater'])).toBe('Stopped in floodwater.')
    expect(riskSummary([])).toBe('')
  })
})
