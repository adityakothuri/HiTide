import { describe, expect, it } from 'vitest'
import { stepText } from './stepText'

describe('stepText', () => {
  it('reads a HELP entry as asking for help', () => {
    expect(stepText('HELP from driver -> responders flagged')).toBe('Asked for help · responders flagged')
    expect(stepText('HELP from contact -> responders flagged')).toBe('Contact asked for help · responders flagged')
  })

  it('keeps ladder steps and plain notes as before', () => {
    expect(stepText('danger -> voice:danger_call')).toBe('Called (danger)')
    expect(stepText('critical -> sms:x, poll:y')).toBe('Texted, Sent a safe/help poll (critical)')
    expect(stepText('assistant call: Caller trapped')).toBe('Assistant call: Caller trapped')
  })
})
