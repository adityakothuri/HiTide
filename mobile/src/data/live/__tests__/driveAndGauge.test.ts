import { describe, expect, it } from '@jest/globals';
import { buildGauge, buildTrip } from '@/data/fixtures';
import { buildDrivePlan, DEMO_STOP } from '@/data/live/demoDrive';
import { toGauge } from '@/data/live/mapGauge';
import { readLiveConfig } from '@/data/live/config';
import { isDangerEventFor, parseGauges } from '@/data/live/schema';
import { toRoutePoints } from '@/data/live/transport';

const NOW = '2026-11-08T15:00:00.000Z';

describe('buildDrivePlan', () => {
  const route = buildTrip(NOW).routes.original.coords;
  const plan = buildDrivePlan(route);

  it('drives the usual route at town speed and ends stopped on the crossing', () => {
    expect(plan.length).toBeGreaterThan(8);
    expect(plan[0]).toMatchObject({ lat: route[0][1], lon: route[0][0] });
    expect(plan[0].speed_mps).toBeGreaterThan(10);
    const last = plan[plan.length - 1];
    expect(last).toEqual({ lat: DEMO_STOP[1], lon: DEMO_STOP[0], speed_mps: 0 });
  });

  it('is empty for an empty route', () => {
    expect(buildDrivePlan([])).toEqual([]);
  });
});

describe('toGauge', () => {
  const sample = buildGauge(NOW, false);
  const reading = (stage: number, observed: number, rate = 1.2) =>
    parseGauges([{ site: '08166200', name: 'Guadalupe Rv at Kerrville', stage_ft: stage, observed_at: observed, rate_ft_per_hr: rate, flood_category: 'major', online: true }])!;

  it('replaces the sample card with the real reading, without inventing an action stage', () => {
    const g = toGauge(reading(30.1, 1751630400), sample, 'replay of July 4, 2025')!;
    expect(g).toMatchObject({ id: 'usgs-08166200', name: 'Guadalupe River at Kerrville', stageFt: 30.1, actionStageFt: null, floodCategory: 'major', trend: 'rising' });
    expect(g.source).toBe('USGS 08166200 · replay of July 4, 2025');
    expect(g.series).toEqual([30.1]);
  });

  it('appends new readings and keeps the series when the reading is unchanged', () => {
    const a = toGauge(reading(30.1, 1751630400), sample, null)!;
    const b = toGauge(reading(31.0, 1751631300), a, null)!;
    expect(b.series).toEqual([30.1, 31.0]);
    expect(b.seriesStepMinutes).toBeCloseTo(15);
    expect(toGauge(reading(31.0, 1751631300), b, null)!.series).toEqual([30.1, 31.0]);
  });

  it('a "none" flood category is no category (never "None flooding")', () => {
    const none = parseGauges([{ site: '08166200', name: 'x', stage_ft: 1, observed_at: 1751600000, flood_category: 'none' }])!;
    expect(toGauge(none, sample, null)?.floodCategory).toBeNull();
  });

  it('returns null when the gauge is missing or offline', () => {
    expect(toGauge([], sample, null)).toBeNull();
    const offline = parseGauges([{ site: '08166200', name: 'x', stage_ft: 3, observed_at: 1, online: false }])!;
    expect(toGauge(offline, sample, null)).toBeNull();
  });
});

describe('readLiveConfig', () => {
  it('is off without a URL', () => {
    expect(readLiveConfig({})).toBeNull();
    expect(readLiveConfig({ apiUrl: '  ' })).toBeNull();
  });

  it('derives the WebSocket URL and defaults the user', () => {
    expect(readLiveConfig({ apiUrl: 'http://192.168.1.20:8000/' })).toEqual({
      apiUrl: 'http://192.168.1.20:8000',
      wsUrl: 'ws://192.168.1.20:8000/ws',
      userId: 'hc-dana',
    });
  });

  it('fails loudly on a malformed URL or user id', () => {
    expect(() => readLiveConfig({ apiUrl: 'javascript:alert(1)' })).toThrow(/EXPO_PUBLIC_API_URL/);
    expect(() => readLiveConfig({ apiUrl: 'http://localhost:8000/../x' })).toThrow();
    expect(() => readLiveConfig({ apiUrl: 'http://localhost:8000', userId: '../admin' })).toThrow(/USER_ID/);
  });
});

describe('transport helpers', () => {
  it('sends [lat, lon] pairs, thinned to the API limit', () => {
    expect(toRoutePoints([[-99.1, 30.0]])).toEqual([[30.0, -99.1]]);
    const long = Array.from({ length: 5000 }, (_, i) => [-99 + i * 1e-5, 30] as const);
    const pts = toRoutePoints(long);
    expect(pts.length).toBeLessThanOrEqual(2000);
    expect(pts[pts.length - 1]).toEqual([30, long[4999][0]]);
  });

  it('ignores WebSocket events for other users', () => {
    expect(isDangerEventFor({ type: 'user.danger', seq: 1, ts: 'x', payload: { user_id: 'hc-dana', level: 'danger' } }, 'hc-dana')).toBe(true);
  });
});
