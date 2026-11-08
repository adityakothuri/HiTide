import { describe, expect, it } from '@jest/globals';
import type { LngLat } from '@/domain/types';
import { makeProjector, regionAround, unproject } from '@/map/geo';

describe('unproject', () => {
  const region = regionAround([-99.13361, 30.03785], 0.042);

  it('inverts makeProjector exactly (lng/lat -> pixels -> lng/lat)', () => {
    for (const [w, h] of [[390, 844], [430, 300], [1024, 768]]) {
      const project = makeProjector(region, w, h);
      for (const p of [[-99.13361, 30.03785], [-99.15, 30.05], [-99.11, 30.02]] as LngLat[]) {
        const [lon, lat] = unproject(region, w, h, project(p));
        expect(lon).toBeCloseTo(p[0], 10);
        expect(lat).toBeCloseTo(p[1], 10);
      }
    }
  });

  it('the view centre is the region centre, and up is north', () => {
    expect(unproject(region, 400, 600, [200, 300])).toEqual([region.longitude, region.latitude]);
    const [, north] = unproject(region, 400, 600, [200, 0]);
    expect(north).toBeGreaterThan(region.latitude);
  });
});
