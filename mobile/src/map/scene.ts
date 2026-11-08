import type { AppState, LngLat } from '@/domain/types';
import { type Region, regionAround, regionFor } from './geo';

export type LineKind = 'selected' | 'original';
export type MarkerKind = 'user' | 'heading' | 'destination' | 'closure';

export interface MapScene {
  region: Region;
  lines: { id: string; kind: LineKind; coords: readonly LngLat[] }[];
  markers: { id: string; kind: MarkerKind; at: LngLat; label: string }[];
  /** Text labels used only by the local vector fallback (native maps label themselves). */
  labels: { text: string; at: LngLat; kind: 'town' | 'water' | 'road' }[];
}

export type SceneVariant = 'overview' | 'route' | 'alert' | 'location';

const LABELS: MapScene['labels'] = [
  { text: 'Kerrville', at: [-99.1345, 30.0445], kind: 'town' },
  { text: 'Guadalupe River', at: [-99.1300, 30.0262], kind: 'water' },
  { text: 'Riverside Dr', at: [-99.1205, 30.0170], kind: 'road' },
  { text: 'Memorial Blvd', at: [-99.1108, 30.0262], kind: 'road' },
];

/** Describes what each screen's map shows. Pure, so the native map and vector fallback agree. */
export function buildScene(state: AppState, variant: SceneVariant): MapScene {
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
    const approach = trip.routes.original.coords.slice(0, 15);
    return {
      region: regionAround([-99.1192, 30.0146], 0.008),
      lines: [{ id: 'approach', kind: 'selected', coords: approach }],
      markers: [
        { id: 'you', kind: 'heading', at: trip.origin, label: 'Your position' },
        ...(closure ? [{ id: 'closure', kind: 'closure' as const, at: closure.at, label: `Closure on ${closure.road}` }] : []),
      ],
      labels: LABELS.filter((l) => l.kind !== 'town'),
    };
  }

  if (variant === 'location') {
    return {
      region: regionAround(caseAt, 0.016),
      lines: [],
      markers: [{ id: 'you', kind: 'user', at: caseAt, label: 'Your location' }],
      labels: LABELS,
    };
  }

  return {
    region: regionAround([-99.1290, 30.0325], 0.042),
    lines: [],
    markers: [{ id: 'you', kind: 'user', at: trip.origin, label: 'Your location near home' }],
    labels: LABELS,
  };
}
