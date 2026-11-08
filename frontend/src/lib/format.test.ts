import { describe, expect, it } from 'vitest'
import { ageBand, firstName, formatClock, formatDepth, formatDistance, formatRelative, sentenceCase } from './format'

const MIN = 60_000

describe('formatClock', () => {
  it('formats in Central time as h:mm AM/PM', () => {
    expect(formatClock('2026-11-08T02:42:00Z')).toBe('8:42 PM')
  })
  it('returns an em dash for an invalid date', () => {
    expect(formatClock('nope')).toBe('—')
  })
})

describe('formatRelative', () => {
  const now = Date.parse('2026-11-08T03:00:00Z')
  it('says "Just now" under a minute', () => {
    expect(formatRelative('2026-11-08T02:59:30Z', now)).toBe('Just now')
  })
  it('uses minutes under an hour', () => {
    expect(formatRelative(new Date(now - 4 * MIN).toISOString(), now)).toBe('4 min ago')
  })
  it('uses hours and minutes past an hour', () => {
    expect(formatRelative(new Date(now - 65 * MIN).toISOString(), now)).toBe('1 hr 5 min ago')
  })
  it('treats a future time as just now', () => {
    expect(formatRelative(new Date(now + 5 * MIN).toISOString(), now)).toBe('Just now')
  })
})

describe('formatDepth', () => {
  it('rounds to whole inches', () => {
    expect(formatDepth(14.4)).toBe('14 in')
  })
  it('says less than 1 in for a trace', () => {
    expect(formatDepth(0.3)).toBe('Less than 1 in')
  })
  it('switches to feet and inches at 3 ft', () => {
    expect(formatDepth(40)).toBe('3 ft 4 in')
  })
})

describe('formatDistance', () => {
  it('uses feet rounded to 50 under a tenth of a mile', () => {
    expect(formatDistance(150)).toBe('500 ft')
  })
  it('uses miles with one decimal otherwise', () => {
    expect(formatDistance(4672.9)).toBe('2.9 miles')
  })
  it('uses the singular for exactly one mile', () => {
    expect(formatDistance(1609.34)).toBe('1 mile')
  })
})

describe('ageBand', () => {
  it.each([
    [16, 'Under 18'],
    [22, '18–24'],
    [34, '25–34'],
    [49, '35–49'],
    [64, '50–64'],
    [70, '65–74'],
    [78, '75+'],
  ])('%i is %s', (age, band) => {
    expect(ageBand(age)).toBe(band)
  })
})

describe('firstName', () => {
  it('takes the first word', () => {
    expect(firstName('Margaret Hale')).toBe('Margaret')
    expect(firstName('Margaret H.')).toBe('Margaret')
  })
  it('handles an empty name', () => {
    expect(firstName('')).toBe('Unknown driver')
  })
})

describe('sentenceCase', () => {
  it('lowercases every word after the first', () => {
    expect(sentenceCase('Flash Flood Warning')).toBe('Flash flood warning')
  })
  it('keeps acronyms', () => {
    expect(sentenceCase('NWS Flood Watch')).toBe('NWS flood watch')
  })
})
