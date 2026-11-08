import { describe, expect, it } from 'vitest'
import { streetFromText } from './geo'

describe('streetFromText', () => {
  it('finds the street in pre-trip copy', () => {
    expect(streetFromText('Your usual route to work crosses flooded roads at Riverside Drive. Use the safer route')).toBe('Riverside Drive')
  })
  it('finds the street in call copy', () => {
    expect(streetFromText('Your car looks stopped in floodwater on Water Street. Are you safe?')).toBe('Water Street')
  })
  it('returns null when no street is named', () => {
    expect(streetFromText('Flooded road ahead. Turn around.')).toBeNull()
    expect(streetFromText(undefined)).toBeNull()
  })
})
