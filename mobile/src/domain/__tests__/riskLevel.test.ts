import { describe, expect, it } from '@jest/globals';
import { LEVEL_LABEL, levelTone, pointTone } from '@/domain/riskLevel';

describe('risk tones match the dashboard', () => {
  it('critical and danger share the critical tone; warning is amber; the rest muted', () => {
    expect(levelTone('critical')).toBe('critical');
    expect(levelTone('danger')).toBe('critical');
    expect(levelTone('warning')).toBe('warning');
    expect(levelTone('watch')).toBe('muted');
    expect(levelTone(null)).toBe('muted');
  });

  it('crossings: confirmed critical, likely warning, unknown muted (never "open")', () => {
    expect(pointTone('confirmed_flooded')).toBe('critical');
    expect(pointTone('likely_flooded')).toBe('warning');
    expect(pointTone('unknown')).toBe('muted');
    expect(LEVEL_LABEL.danger).toBe('Danger');
  });
});
