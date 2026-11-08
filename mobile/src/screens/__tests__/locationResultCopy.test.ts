import { describe, expect, it } from '@jest/globals';
import type { DangerLevel } from '@/domain/types';
import { formatLngLat, locationResultCopy, wasTexted } from '../locationResultCopy';

describe('locationResultCopy', () => {
  it('warning: flooding near you, go back the way you came, with directions', () => {
    const c = locationResultCopy('warning', 'warning -> text:warning');
    expect(c).toMatchObject({
      tone: 'warning',
      headline: 'Flooding near you',
      body: 'Go back the way you came and follow these directions.',
      showDirections: true,
      textLine: 'We texted you these directions',
    });
  });

  it('warning without a text yet says one is on its way', () => {
    expect(locationResultCopy('warning', null).textLine).toBe('A text with these directions is on its way');
    expect(locationResultCopy('warning', 'warning -> tts_in_app:warning').textLine).toBe('A text with these directions is on its way');
  });

  it.each(['danger', 'critical'] as DangerLevel[])('%s: a dangerous area, HiTide is calling', (level) => {
    const c = locationResultCopy(level, 'critical -> voice:critical_call');
    expect(c.tone).toBe('critical');
    expect(`${c.headline} ${c.body}`).toBe('You’re in a dangerous area. HiTide is calling you now.');
    expect(c.showDirections).toBe(false);
  });

  it.each(['watch', 'none', null] as (DangerLevel | null)[])('%s: no flooding reported, never "safe"', (level) => {
    const c = locationResultCopy(level, null);
    expect(c.tone).toBe('muted');
    expect(c.headline).toBe('No flooding reported where you are');
    expect(`${c.headline} ${c.body}`.toLowerCase()).not.toContain('safe');
  });

  it('recognises a text in a combined ladder entry, and formats a pin as lat, lon', () => {
    expect(wasTexted('warning -> poll:x, text:warning')).toBe(true);
    expect(wasTexted('family contacted (no reply)')).toBe(false);
    expect(formatLngLat([-99.13361, 30.03785])).toBe('30.03785, -99.13361');
  });
});
