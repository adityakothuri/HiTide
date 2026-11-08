import { nearestIndex, sampleAlong } from '@/domain/routeGeometry';
import type { LngLat } from '@/domain/types';
import type { LocationPing } from './transport';

/**
 * The development demo drive: Dana's usual route to work, ending stopped on a low-water crossing.
 * Park Street over Quinlan Creek (backend point cp-0043) is confirmed flooded in the July 4, 2025 replay
 * from about 06:45 CDT; earlier in the replay the backend correctly raises nothing there.
 */
export const DEMO_STOP: LngLat = [-99.13361, 30.03785];

const DRIVE_SPEED_MPS = 13.4; // ~30 mph in town
const STEP_M = 150;
const STOP_PINGS = 3;

export function buildDrivePlan(route: readonly LngLat[], stop: LngLat = DEMO_STOP): LocationPing[] {
  if (route.length === 0) return [];
  const end = nearestIndex(route, stop);
  const driving = sampleAlong(route, STEP_M, 0, end).map(([lon, lat]) => ({ lat, lon, speed_mps: DRIVE_SPEED_MPS }));
  const stopped = Array.from({ length: STOP_PINGS }, () => ({ lat: stop[1], lon: stop[0], speed_mps: 0 }));
  return [...driving, ...stopped];
}
