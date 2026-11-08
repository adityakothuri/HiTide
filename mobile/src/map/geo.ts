import type { LngLat } from '@/domain/types';

export interface Region {
  latitude: number;
  longitude: number;
  latitudeDelta: number;
  longitudeDelta: number;
}

const MIN_DELTA = 0.004;

/** Region that contains every point with a fractional margin. */
export function regionFor(points: readonly LngLat[], margin = 0.25): Region {
  const lons = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  return {
    latitude: (minLat + maxLat) / 2,
    longitude: (minLon + maxLon) / 2,
    latitudeDelta: Math.max((maxLat - minLat) * (1 + margin * 2), MIN_DELTA),
    longitudeDelta: Math.max((maxLon - minLon) * (1 + margin * 2), MIN_DELTA),
  };
}

export function regionAround(center: LngLat, delta: number): Region {
  return { latitude: center[1], longitude: center[0], latitudeDelta: delta, longitudeDelta: delta };
}

export const toLatLng = (p: LngLat): { latitude: number; longitude: number } => ({ latitude: p[1], longitude: p[0] });

/**
 * Projects lng/lat to view pixels so the whole region fits in the view (as native maps do),
 * using an equirectangular projection corrected for latitude.
 */
export function makeProjector(region: Region, width: number, height: number) {
  const k = Math.cos((region.latitude * Math.PI) / 180);
  const spanX = region.longitudeDelta * k;
  const spanY = region.latitudeDelta;
  const scale = Math.min(width / spanX, height / spanY);
  return (p: LngLat): [number, number] => [
    width / 2 + (p[0] - region.longitude) * k * scale,
    height / 2 - (p[1] - region.latitude) * scale,
  ];
}

/** The exact inverse of `makeProjector`: view pixels back to lng/lat (e.g. where a finger tapped the map). */
export function unproject(region: Region, width: number, height: number, [x, y]: readonly [number, number]): LngLat {
  const k = Math.cos((region.latitude * Math.PI) / 180);
  const spanX = region.longitudeDelta * k;
  const spanY = region.latitudeDelta;
  const scale = Math.min(width / spanX, height / spanY);
  return [region.longitude + (x - width / 2) / (k * scale), region.latitude - (y - height / 2) / scale];
}
