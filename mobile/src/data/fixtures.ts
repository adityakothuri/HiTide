import type {
  EmergencyContact,
  FloodWarning,
  GaugeReading,
  LngLat,
  Preferences,
  Trip,
  UpdateItem,
  UserProfile,
} from '@/domain/types';
import geo from './geo/kerrville.json';

/**
 * Deterministic demo fixtures. Geometry comes from the cached Kerrville road graph
 * (data/town/graph.graphml); conditions, times, and people are illustrative.
 */

const toLngLat = (c: number[]): LngLat => [c[0], c[1]] as const;

export const MAP_GEO = {
  bbox: geo.bbox as [number, number, number, number],
  river: geo.river.map((line) => line.map(toLngLat)),
  roads: geo.roads.map((r) => ({ major: r.k === 'major', coords: r.c.map(toLngLat) })),
};

export const DEMO_USER: UserProfile = {
  id: 'user-dana',
  firstName: 'Dana',
  fullName: 'Dana Whitfield',
  initials: 'DW',
  homeArea: 'Kerrville, Texas',
};

export const DEFAULT_CONTACT: EmergencyContact = {
  name: 'Maria Whitfield',
  relationship: 'Sister',
  phone: '(830) 555-0142',
};

export const DEFAULT_PREFERENCES: Preferences = {
  spokenAlerts: true,
  locationSharing: false,
};

const METERS_PER_MILE = 1609.34;
const toMiles = (m: number): number => Math.round((m / METERS_PER_MILE) * 10) / 10;

export const CLOSURE_POINT: LngLat = [-99.1214, 30.0161];

export function buildTrip(nowIso: string): Trip {
  return {
    id: 'trip-work',
    name: 'Your trip to work',
    from: 'Home',
    to: 'Work',
    origin: toLngLat(geo.home),
    destination: toLngLat(geo.work),
    routes: {
      original: {
        id: 'original',
        label: 'Usual route',
        via: 'Riverside Dr',
        distanceMi: toMiles(geo.original.m),
        durationMin: 9,
        coords: geo.original.coords.map(toLngLat),
        affectedRoad: 'Riverside Drive',
      },
      alternate: {
        id: 'alternate',
        label: 'Alternate route',
        via: 'Memorial Blvd',
        distanceMi: toMiles(geo.alternate.m),
        durationMin: 11,
        coords: geo.alternate.coords.map(toLngLat),
        affectedRoad: null,
      },
    },
    closure: {
      road: 'Riverside Drive',
      at: CLOSURE_POINT,
      source: 'Community report (sample data)',
      reportedAt: minutesFrom(nowIso, -56),
    },
  };
}

const MS_PER_MINUTE = 60_000;

/** Demo times are relative to "now" so fixture events always precede live ones. */
export function minutesFrom(nowIso: string, minutes: number): string {
  return new Date(new Date(nowIso).getTime() + minutes * MS_PER_MINUTE).toISOString();
}

export function buildWarning(nowIso: string): FloodWarning {
  return {
    id: 'warning-kerr-ffw',
    event: 'Flash Flood Warning',
    area: 'Kerr County',
    source: 'National Weather Service (sample data)',
    issuedAt: minutesFrom(nowIso, -64),
    expiresAt: minutesFrom(nowIso, 240),
    summary:
      'Heavy rain upstream may cause the Guadalupe River and low-water crossings near Kerrville to rise quickly.',
    guidance: 'Avoid low-water crossings. Never drive through floodwater. Turn around, don’t drown.',
  };
}

export const UPDATE_IDS = {
  warning: 'upd-warning',
  routeChanged: 'upd-route-changed',
  routeSelected: 'upd-route-selected',
  contact: 'upd-contact',
  turnAround: 'upd-turn-around',
  checkIn: 'upd-check-in',
  help: 'upd-help',
  safe: 'upd-safe',
} as const;

export function warningUpdate(nowIso: string): UpdateItem {
  return {
    id: UPDATE_IDS.warning,
    category: 'general',
    icon: 'warning',
    title: 'Flood warning near home',
    body: 'Kerr County · National Weather Service',
    at: minutesFrom(nowIso, -64),
    target: 'warning',
    actionLabel: 'View warning',
  };
}

export function routeChangedUpdate(nowIso: string): UpdateItem {
  return {
    id: UPDATE_IDS.routeChanged,
    category: 'trips',
    icon: 'car',
    title: 'Your work route has changed',
    body: 'A reported closure affects Riverside Drive',
    at: minutesFrom(nowIso, -53),
    target: 'route',
    actionLabel: 'Review route',
  };
}

export function contactUpdate(nowIso: string, contactName: string): UpdateItem {
  return {
    id: UPDATE_IDS.contact,
    category: 'general',
    icon: 'person',
    title: 'Your contact is up to date',
    body: `${contactName} is your emergency contact`,
    at: minutesFrom(nowIso, -91),
    target: 'contact',
  };
}

const RISING_SERIES = [5.8, 6.0, 6.3, 6.9, 7.6, 8.4, 9.1, 9.6] as const;
const STEADY_SERIES = [3.1, 3.1, 3.0, 3.1, 3.1, 3.0, 3.0, 3.1] as const;

/** Guadalupe River at Kerrville. Stage values are illustrative sample data. */
export function buildGauge(nowIso: string, isRising: boolean): GaugeReading {
  const series = isRising ? RISING_SERIES : STEADY_SERIES;
  return {
    id: 'usgs-08166200',
    name: 'Guadalupe River at Kerrville',
    stageFt: series[series.length - 1],
    actionStageFt: 12,
    trend: isRising ? 'rising' : 'steady',
    series,
    observedAt: minutesFrom(nowIso, -6),
    source: 'USGS gauge (sample data)',
  };
}
