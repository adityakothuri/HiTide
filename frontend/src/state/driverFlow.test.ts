import { describe, expect, it } from 'vitest'
import { deriveDriverScreen, helpSteps } from './driverFlow'
import { caseAt, makeDrone } from './fixtures'

const base = { alertActive: true, hasPretrip: false, turnAround: false, turnAroundDismissed: false, case: null, reply: null } as const

describe('deriveDriverScreen', () => {
  it('is calm with nothing happening', () => {
    expect(deriveDriverScreen({ ...base, alertActive: false })).toBe('calm')
  })
  it('is calm during a warning that does not touch this driver', () => {
    expect(deriveDriverScreen(base)).toBe('calm')
  })
  it('shows the warning when this driver got a pre-trip text', () => {
    expect(deriveDriverScreen({ ...base, hasPretrip: true })).toBe('warning')
  })
  it('takes over with the en-route alert', () => {
    expect(deriveDriverScreen({ ...base, hasPretrip: true, turnAround: true })).toBe('en_route')
  })
  it('goes to the rerouted warning view after "Show new route"', () => {
    expect(deriveDriverScreen({ ...base, turnAround: true, turnAroundDismissed: true })).toBe('warning')
  })
  it('asks for a check-in while the case is early', () => {
    expect(deriveDriverScreen({ ...base, case: caseAt('calling') })).toBe('check_in')
    expect(deriveDriverScreen({ ...base, case: caseAt('contacting_family') })).toBe('check_in')
  })
  it('shows help on the way when the driver asks for help', () => {
    expect(deriveDriverScreen({ ...base, case: caseAt('calling'), reply: 'need_help' })).toBe('help')
  })
  it('shows help on the way once the drone is dispatched', () => {
    expect(deriveDriverScreen({ ...base, case: caseAt('drone_en_route') })).toBe('help')
    expect(deriveDriverScreen({ ...base, case: caseAt('handed_to_responders') })).toBe('help')
  })
  it('shows the claim once safe or resolved', () => {
    expect(deriveDriverScreen({ ...base, case: caseAt('calling'), reply: 'safe' })).toBe('after')
    expect(deriveDriverScreen({ ...base, case: caseAt('resolved') })).toBe('after')
  })
  it('a case outranks a turn-around', () => {
    expect(deriveDriverScreen({ ...base, turnAround: true, case: caseAt('calling') })).toBe('check_in')
  })
})

describe('helpSteps', () => {
  const timeline = [
    { ts: '2026-11-08T02:42:00Z', t_case_s: 0, kind: 'flag', text: 'High risk: responders flagged immediately' },
    { ts: '2026-11-08T02:42:00Z', t_case_s: 0, kind: 'outreach', text: 'Voice call to driver (mock, sent): no answer yet' },
    { ts: '2026-11-08T02:42:12Z', t_case_s: 12, kind: 'state', text: 'Contacting family' },
    { ts: '2026-11-08T02:42:18Z', t_case_s: 18, kind: 'drone', text: 'Drone dispatched' },
  ]

  it('marks steps done, in progress or waiting from the case state', () => {
    const steps = helpSteps(caseAt('drone_en_route', { timeline, responder_flag: false }), makeDrone({ eta_s: 120 }), 'Maria')
    expect(steps.map((s) => [s.key, s.status])).toEqual([
      ['called', 'done'],
      ['contact', 'done'],
      ['drone', 'active'],
      ['rescue', 'waiting'],
    ])
    expect(steps[1].label).toBe('We contacted Maria')
    expect(steps[2].detail).toBe('Arriving in 2 min')
    expect(steps[0].ts).toBe('2026-11-08T02:42:00Z')
  })

  it('marks the rescue team notified when responders are flagged', () => {
    const steps = helpSteps(caseAt('drone_en_route', { timeline, responder_flag: true }), null, 'Maria')
    expect(steps[3].status).toBe('done')
    expect(steps[3].ts).toBe('2026-11-08T02:42:00Z')
  })

  it('marks the drone done once on scene', () => {
    const steps = helpSteps(caseAt('drone_en_route', { timeline }), makeDrone({ status: 'on_scene', eta_s: 0 }), 'Maria')
    expect(steps[2].status).toBe('done')
    expect(steps[2].detail).toBe('At your car')
  })

  it('leaves later steps waiting early in the case', () => {
    const steps = helpSteps(caseAt('calling', { timeline: [], responder_flag: false }), null, 'Maria')
    expect(steps.map((s) => s.status)).toEqual(['done', 'waiting', 'waiting', 'waiting'])
  })
})
