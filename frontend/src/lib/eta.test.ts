import { describe, expect, it } from 'vitest'
import { formatEta, minutesGained } from './eta'

describe('minutesGained', () => {
  it('is crew arrival minus drone arrival, in whole minutes', () => {
    expect(minutesGained(16 * 60, 2 * 60)).toBe(14)
  })
  it('rounds to the nearest minute', () => {
    expect(minutesGained(600, 15)).toBe(10)
  })
  it('never goes below zero', () => {
    expect(minutesGained(60, 300)).toBe(0)
  })
  it('is null when either ETA is unknown', () => {
    expect(minutesGained(null, 60)).toBeNull()
    expect(minutesGained(600, undefined)).toBeNull()
  })
})

describe('formatEta', () => {
  it('says "Arriving now" under 10 seconds', () => {
    expect(formatEta(4)).toBe('Arriving now')
  })
  it('uses seconds under a minute', () => {
    expect(formatEta(42)).toBe('42 s')
  })
  it('uses whole minutes, rounded up', () => {
    expect(formatEta(61)).toBe('2 min')
  })
  it('uses hours past an hour', () => {
    expect(formatEta(3900)).toBe('1 hr 5 min')
  })
})
