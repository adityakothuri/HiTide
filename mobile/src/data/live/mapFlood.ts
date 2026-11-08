import type { Directions, FloodLayer, FloodStatus, LngLat, RouteChoice } from '@/domain/types';
import type { RemoteDirections, RemoteFloodLayer, RemoteRouteOptions } from './schema';

/** Pure mappers from validated backend payloads to the shapes the map draws. */

const REPLAY_PREFIX = /^REPLAY of [^:]+:\s*/;

const toLngLat = (c: readonly [number, number]): LngLat => [c[0], c[1]];

const uniqueBy = <T,>(items: readonly T[], key: (t: T) => string): T[] => {
  const seen = new Set<string>();
  return items.filter((t) => {
    const k = key(t);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
};

export function toFloodLayer(remote: RemoteFloodLayer): FloodLayer {
  return {
    at: remote.at ?? null,
    roads: uniqueBy(remote.segments, (s) => s.id).map((s) => ({
      id: s.id,
      name: s.name ?? 'Unnamed road',
      status: s.status as FloodStatus,
      coords: s.coords.map(toLngLat),
    })),
    points: uniqueBy(remote.points, (p) => p.id).map((p) => ({
      id: p.id,
      name: p.name ?? 'Crossing',
      kind: p.kind ?? 'crossing',
      status: p.status as FloodStatus,
      at: [p.lon, p.lat],
    })),
    gauges: remote.gauges.map((g) => ({
      site: g.site,
      name: g.name.replace(/\bRv\b/g, 'River'),
      at: [g.lon, g.lat],
      stageFt: g.stage_ft ?? null,
      category: g.flood_category && g.flood_category !== 'none' ? g.flood_category : null,
    })),
    alerts: [
      ...new Set(remote.alerts.map((a) => (a.headline ?? '').replace(REPLAY_PREFIX, '').trim()).filter(Boolean)),
    ],
    sample: false,
    replay: remote.mode === 'replay',
  };
}

export function toDirections(remote: RemoteDirections): Directions {
  return {
    text: remote.text,
    kind: remote.kind,
    roadNames: remote.road_names,
    lengthM: remote.length_m,
    lines: remote.coords.map((line) => line.map(toLngLat)),
    avoid: remote.avoid,
  };
}

export interface FloodCounts {
  flooded: number;
  likely: number;
  crossingsFlooded: number;
}

export function floodCounts(layer: FloodLayer): FloodCounts {
  return {
    flooded: layer.roads.filter((r) => r.status === 'confirmed_flooded').length,
    likely: layer.roads.filter((r) => r.status === 'likely_flooded').length,
    crossingsFlooded: layer.points.filter((p) => p.status === 'confirmed_flooded' || p.status === 'likely_flooded')
      .length,
  };
}

const STATUS_RANK: Record<RouteChoice['status'], number> = { clear: 0, likely: 1, flooded: 2 };

/** Least reported flooding on top (then quickest). The backend orders them too; this keeps the rule in one view. */
export function byLeastFlooding(a: RouteChoice, b: RouteChoice): number {
  return (
    STATUS_RANK[a.status] - STATUS_RANK[b.status] ||
    a.flooded.length + a.likely.length - (b.flooded.length + b.likely.length) ||
    a.minutes - b.minutes
  );
}

export function toRouteChoices(remote: RemoteRouteOptions): RouteChoice[] {
  return remote.options
    .map((o) => ({
    id: o.id,
    label: o.label,
    via: o.via,
    lengthM: o.length_m,
    minutes: o.minutes,
    status: o.status,
    flooded: o.flooded,
    likely: o.likely,
    lines: o.coords.map((line) => line.map(toLngLat)),
    }))
    .sort(byLeastFlooding);
}
