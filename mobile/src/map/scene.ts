import type { AppState, FloodLayer, FloodStatus, LngLat } from '@/domain/types';
import { STATUS_LABEL } from './floodStyle';
import { nearestIndex } from '@/domain/routeGeometry';
import { type Region, regionAround, regionFor } from './geo';

export type LineKind = 'selected' | 'original' | 'option';
export type MarkerKind = 'user' | 'heading' | 'destination' | 'closure' | 'pin';

export interface MapScene {
  region: Region;
  lines: { id: string; kind: LineKind; coords: readonly LngLat[] }[];
  markers: { id: string; kind: MarkerKind; at: LngLat; label: string }[];
  /** Text labels used only by the local vector fallback (native maps label themselves). */
  labels: { text: string; at: LngLat; kind: 'town' | 'water' | 'road' }[];
  /** The dashboard's flood layers: roads by status, crossings, gauges. Empty when there is no flood picture. */
  flood: {
    roads: { id: string; status: FloodStatus; coords: readonly LngLat[]; label: string }[];
    points: { id: string; status: FloodStatus; at: LngLat; label: string }[];
    gauges: { id: string; category: string | null; at: LngLat; label: string }[];
  };
  /** A way to higher ground, drawn on the check-in and support maps. */
  directions: readonly (readonly LngLat[])[];
}

const NO_FLOOD: MapScene['flood'] = { roads: [], points: [], gauges: [] };

const FEATURES = new WeakMap<FloodLayer, MapScene['flood']>();

/**
 * The flood layers as map features, with spoken labels for screen readers. Cached per layer object, so a poll that
 * brings no change keeps the same arrays and the map's memoized overlay skips re-rendering hundreds of roads.
 */
export function floodFeatures(layer: FloodLayer | null): MapScene['flood'] {
  if (!layer) return NO_FLOOD;
  const cached = FEATURES.get(layer);
  if (cached) return cached;
  const features = computeFeatures(layer);
  FEATURES.set(layer, features);
  return features;
}

function computeFeatures(layer: FloodLayer): MapScene['flood'] {
  return {
    roads: layer.roads.map((r) => ({ id: r.id, status: r.status, coords: r.coords, label: `${r.name}, ${STATUS_LABEL[r.status]}` })),
    // Only crossings with water get a dot; unchecked ones stay off the map (their roads carry the hairline).
    points: layer.points
      .filter((p) => p.status === 'confirmed_flooded' || p.status === 'likely_flooded')
      .map((p) => ({ id: p.id, status: p.status, at: p.at, label: `${p.name} ${p.kind}, ${STATUS_LABEL[p.status]}` })),
    gauges: layer.gauges.map((g) => ({
      id: g.site,
      category: g.category,
      at: g.at,
      label: `${g.name} gauge${g.stageFt !== null ? `, ${g.stageFt.toFixed(1)} feet` : ''}${g.category ? `, ${g.category} flooding` : ''}`,
    })),
  };
}

export type SceneVariant = 'overview' | 'route' | 'alert' | 'location' | 'flood';

const LABELS: MapScene['labels'] = [
  { text: 'Kerrville', at: [-99.1345, 30.0445], kind: 'town' },
  { text: 'Guadalupe River', at: [-99.1300, 30.0262], kind: 'water' },
  { text: 'Riverside Dr', at: [-99.1205, 30.0170], kind: 'road' },
  { text: 'Memorial Blvd', at: [-99.1108, 30.0262], kind: 'road' },
];

const ALERT_BEHIND = 6;
const ALERT_AHEAD = 12;
const ALERT_DELTA = 0.008;
const SAMPLE_ALERT_CENTER: LngLat = [-99.1192, 30.0146];
const OVERVIEW_CENTER: LngLat = [-99.129, 30.0325];
const OVERVIEW_DELTA = 0.042;

type BaseScene = Omit<MapScene, 'flood' | 'directions'>;

const FLOOD_DELTA = 0.07;
const ROUTE_MARGIN = 0.16;
const DIRECTIONS_MARGIN = 0.3;

/**
 * Describes what each screen's map shows. Pure, so the native map and vector fallback agree.
 * Every map carries the flood layers; the check-in / support map also shows the way to higher ground.
 */
export function buildScene(state: AppState, variant: SceneVariant): MapScene {
  const flood = floodFeatures(state.floodLayer);
  if (variant === 'flood') {
    const base = baseScene(state, 'overview');
    return { ...base, region: regionAround(state.position ?? OVERVIEW_CENTER, FLOOD_DELTA), flood, directions: [] };
  }
  if (variant === 'route' && state.routeChoices.length > 0) {
    // Every option is drawn; the chosen one is bold. Until one is chosen, all are drawn as options.
    const lines: MapScene['lines'] = state.routeChoices.flatMap((c) =>
      c.lines.map((coords, i) => ({
        id: `${c.id}-${i}`,
        kind: c.id === state.selectedChoiceId ? ('selected' as const) : ('option' as const),
        coords,
      })),
    );
    const base = baseScene(state, 'route');
    const all = lines.flatMap((l) => l.coords);
    return { ...base, lines, region: all.length ? regionFor(all, ROUTE_MARGIN) : base.region, flood, directions: [] };
  }
  const base = baseScene(state, variant);
  const shown = focusFlood(flood, variant);
  const directions = variant === 'location' && state.directions ? state.directions.lines : [];
  if (directions.length === 0) return { ...base, flood: shown, directions };
  const you = state.safetyCase?.location ?? state.position ?? state.trip.origin;
  return { ...base, region: regionFor([you, ...directions.flat()], DIRECTIONS_MARGIN), flood: shown, directions };
}

/**
 * Urgent screens show only what changes the next decision: the turn-around map draws confirmed flooding alone; the
 * check-in map adds likely flooding (where not to walk or drive) but no unchecked hairlines or gauges.
 */
function focusFlood(flood: MapScene['flood'], variant: SceneVariant): MapScene['flood'] {
  if (variant === 'alert') {
    return {
      roads: flood.roads.filter((r) => r.status === 'confirmed_flooded'),
      points: flood.points.filter((p) => p.status === 'confirmed_flooded'),
      gauges: [],
    };
  }
  if (variant === 'location') {
    return { roads: flood.roads.filter((r) => r.status !== 'unknown'), points: flood.points, gauges: [] };
  }
  return flood;
}

function baseScene(state: AppState, variant: Exclude<SceneVariant, 'flood'>): BaseScene {
  const { trip } = state;
  const closure = trip.closure;
  const showAlternate = closure !== null;
  const caseAt = state.safetyCase?.location ?? closure?.at ?? trip.origin;

  if (variant === 'route') {
    const usual = trip.routes.original;
    const alt = trip.routes.alternate;
    const lines: MapScene['lines'] = showAlternate
      ? [
          { id: 'original', kind: 'original', coords: usual.coords },
          { id: 'alternate', kind: 'selected', coords: alt.coords },
        ]
      : [{ id: 'usual', kind: 'selected', coords: usual.coords }];
    const markers: MapScene['markers'] = [
      { id: 'origin', kind: 'user', at: trip.origin, label: 'Home, your location' },
      { id: 'dest', kind: 'destination', at: trip.destination, label: 'Work' },
    ];
    if (closure) markers.push({ id: 'closure', kind: 'closure', at: closure.at, label: `Closure on ${closure.road}` });
    return {
      region: regionFor([...usual.coords, ...alt.coords], 0.16),
      lines,
      markers,
      labels: LABELS,
    };
  }

  if (variant === 'alert') {
    const route = trip.routes.original.coords;
    const you = state.position ?? trip.origin;
    const at = state.position ? nearestIndex(route, you) : 0;
    const approach = route.slice(Math.max(0, at - ALERT_BEHIND), at + ALERT_AHEAD);
    const center: LngLat = state.position
      ? closure
        ? [(you[0] + closure.at[0]) / 2, (you[1] + closure.at[1]) / 2]
        : you
      : SAMPLE_ALERT_CENTER;
    const span = state.position && closure ? Math.max(ALERT_DELTA, Math.abs(you[1] - closure.at[1]) * 2.6) : ALERT_DELTA;
    return {
      region: regionAround(center, span),
      lines: [{ id: 'approach', kind: 'selected', coords: approach }],
      markers: [
        { id: 'you', kind: 'heading', at: you, label: 'Your position' },
        ...(closure ? [{ id: 'closure', kind: 'closure' as const, at: closure.at, label: `Closure on ${closure.road}` }] : []),
      ],
      labels: LABELS.filter((l) => l.kind !== 'town'),
    };
  }

  if (variant === 'location') {
    // Without a case, a location the person set on the map (Set location) is where they are.
    const pinned = !state.safetyCase && state.lastPin ? state.lastPin.at : null;
    const at = pinned ?? caseAt;
    return {
      region: regionAround(at, 0.016),
      lines: [],
      markers: [{ id: 'you', kind: pinned ? 'pin' : 'user', at, label: pinned ? 'The location you set' : 'Your location' }],
      labels: LABELS,
    };
  }

  const here = state.position ?? trip.origin;
  return {
    region: regionAround(state.position ?? OVERVIEW_CENTER, OVERVIEW_DELTA),
    lines: [],
    markers: [{ id: 'you', kind: 'user', at: here, label: state.position ? 'Your location' : 'Your location near home' }],
    labels: LABELS,
  };
}
