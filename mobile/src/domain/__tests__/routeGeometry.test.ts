import { describe, expect, it } from '@jest/globals';
import { distanceM, nearestIndex, pointAlong, sampleAlong } from '@/domain/routeGeometry';
import type { LngLat } from '@/domain/types';

// A straight east-west line in Kerrville, vertices ~96 m apart.
const LINE: LngLat[] = [0, 1, 2, 3, 4].map((i) => [-99.13 + i * 0.001, 30.03] as const);

describe('routeGeometry', () => {
  it('measures town-scale distances', () => {
    expect(distanceM(LINE[0], LINE[1])).toBeGreaterThan(90);
    expect(distanceM(LINE[0], LINE[1])).toBeLessThan(100);
  });

  it('finds the nearest vertex', () => {
    expect(nearestIndex(LINE, [-99.1279, 30.0301])).toBe(2);
  });

  it('walks a distance along the route and clamps at the end', () => {
    const half = pointAlong(LINE, 0, distanceM(LINE[0], LINE[1]) / 2);
    expect(half[0]).toBeCloseTo(-99.1295, 4);
    expect(pointAlong(LINE, 1, 10_000)).toEqual(LINE[4]);
  });

  it('samples from the start to the target vertex, inclusive, at the given spacing', () => {
    const pts = sampleAlong(LINE, 150, 0, 3);
    expect(pts[0]).toEqual(LINE[0]);
    expect(pts[pts.length - 1]).toEqual(LINE[3]);
    expect(pts.length).toBeLessThan(4);
  });

  it('clamps out-of-range indices instead of reading outside the route', () => {
    expect(sampleAlong(LINE, 50, -3, 99)).toEqual(LINE);
    expect(sampleAlong([], 50)).toEqual([]);
  });
});
