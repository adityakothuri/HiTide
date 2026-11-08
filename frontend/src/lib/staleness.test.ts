import { describe, expect, it } from 'vitest'
import { STALE_AFTER_MS, isStale } from './staleness'

describe('isStale', () => {
  const now = Date.parse('2026-11-08T03:00:00Z')
  it('is false within 5 minutes', () => {
    expect(isStale('2026-11-08T02:56:00Z', now)).toBe(false)
  })
  it('is true after 5 minutes', () => {
    expect(isStale('2026-11-08T02:54:59Z', now)).toBe(true)
  })
  it('treats missing or invalid times as stale', () => {
    expect(isStale(null, now)).toBe(true)
    expect(isStale('bad', now)).toBe(true)
  })
  it('exposes the threshold', () => {
    expect(STALE_AFTER_MS).toBe(5 * 60_000)
  })
})
