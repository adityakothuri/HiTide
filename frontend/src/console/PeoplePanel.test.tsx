import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { PeoplePanel } from './PeoplePanel'
import type { Person, ResponseState } from '../region/types'

const response = (over: Partial<ResponseState> = {}): ResponseState => ({
  awaiting_reply: false, called: false, call_unanswered: false, family_contacted: false, responders_flagged: false, case_open: false, need_help: false, safe_until: null, timeline: [], ...over,
})
const person = (user_id: string, level: Person['level'], r?: ResponseState): Person => ({ user_id, level, reasons: ['Road ahead flooded'], stopped_in_water: false, location: {}, response: r })

afterEach(cleanup)

const renderPanel = (people: Person[]) =>
  render(<PeoplePanel people={people} total={people.length} names={{ w: 'Wren Help', o: 'Otto Warn', c: 'Cara Crit' }} pick={null} onPick={() => {}} />)

describe('PeoplePanel', () => {
  it('lists a warning-level person who asked for help, first and tagged, with the warning toggle off', () => {
    const help = response({ need_help: true, responders_flagged: true, timeline: [{ t: 1, what: 'assistant call requested' }, { t: 2, what: 'HELP from driver -> responders flagged' }] })
    renderPanel([person('c', 'critical'), person('w', 'warning', help), person('o', 'warning')])
    const rows = screen.getAllByRole('button', { pressed: false }).filter((b) => b.closest('li'))
    expect(rows[0].textContent).toContain('Wren Help')
    expect(screen.getByText('Needs emergency help')).toBeDefined()
    expect(screen.getByText('Asked for help on the HiTide call')).toBeDefined()
    expect(screen.queryByText('Otto Warn')).toBeNull()
  })

  it('says "Asked for help" when there was no call', () => {
    renderPanel([person('w', 'warning', response({ need_help: true, timeline: [{ t: 2, what: 'HELP from driver -> responders flagged' }] }))])
    expect(screen.getByText('Asked for help')).toBeDefined()
  })
})
