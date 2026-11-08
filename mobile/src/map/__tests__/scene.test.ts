import { describe, expect, it } from '@jest/globals';
import { firstSentence } from '@/components/DirectionsCard';
import { roadStyle, gaugeColor, pointColor } from '@/map/floodStyle';
import { buildScene, floodFeatures } from '@/map/scene';
import { initialState, reducer } from '@/state/reducer';
import { flood } from '@/theme/tokens';

const NOW = '2026-11-08T15:00:00.000Z';

describe('flood layers on every map', () => {
  it('sample mode draws the labelled sample picture; normal has none', () => {
    const warned = initialState(NOW);
    expect(warned.floodLayer?.sample).toBe(true);
    expect(buildScene(warned, 'overview').flood.roads.length).toBeGreaterThan(0);
    const calm = reducer(warned, { type: 'set_scenario', scenario: 'normal', now: NOW });
    expect(buildScene(calm, 'overview').flood.roads).toEqual([]);
  });

  it('only crossings with water are drawn as points (unchecked ones stay off the map)', () => {
    const f = floodFeatures({
      at: null,
      roads: [],
      points: [
        { id: 'a', name: 'A', kind: 'crossing', status: 'open', at: [0, 0] },
        { id: 'b', name: 'B', kind: 'bridge', status: 'unknown', at: [0, 0] },
        { id: 'c', name: 'C', kind: 'bridge', status: 'likely_flooded', at: [0, 0] },
      ],
      gauges: [{ site: 'g', name: 'Kerrville', at: [0, 0], stageFt: 30.1, category: 'major' }],
      alerts: [],
      sample: false,
      replay: true,
    });
    expect(f.points.map((p) => p.id)).toEqual(['c']);
    expect(f.points[0].label).toBe('C bridge, likely flooded');
    expect(f.gauges[0].label).toBe('Kerrville gauge, 30.1 feet, major flooding');
  });

  it('the check-in map frames the way to higher ground', () => {
    const s = reducer(initialState(NOW), { type: 'set_scenario', scenario: 'check_in', now: NOW });
    const scene = buildScene(s, 'location');
    expect(scene.directions.length).toBe(1);
    expect(scene.region.latitudeDelta).toBeGreaterThan(0.016);
    expect(buildScene(s, 'overview').directions).toEqual([]);
  });

  it('styles follow the dashboard and never treat unknown as open', () => {
    expect(roadStyle('confirmed_flooded')).toMatchObject({ color: flood.flooded });
    // Subtle: likely is thinner than flooded and translucent; unknown is a fainter hairline. No dashes (they blob).
    expect(roadStyle('likely_flooded')!.width).toBeLessThan(roadStyle('confirmed_flooded')!.width);
    expect(roadStyle('likely_flooded')!.color).toBe(flood.likelySoft);
    expect(roadStyle('likely_flooded')!.dash).toBeUndefined();
    expect(roadStyle('unknown')!.width).toBeLessThan(roadStyle('likely_flooded')!.width);
    expect(roadStyle('open')).toBeNull();
    expect(pointColor('unknown')).toBe(flood.unknown);
    expect(gaugeColor('major')).toBe(flood.gaugeMajor);
    expect(gaugeColor(null)).toBe(flood.gaugeBelow);
  });
});

describe('assistant line in the case timeline', () => {
  it('a tap adds one assistant step to the open case', () => {
    const s = reducer(initialState(NOW), { type: 'set_scenario', scenario: 'help_requested', now: NOW });
    const once = reducer(s, { type: 'assistant_requested', line: { mode: 'mock', phone: null, requestedAt: NOW } });
    const twice = reducer(once, { type: 'assistant_requested', line: { mode: 'mock', phone: null, requestedAt: NOW } });
    const steps = twice.safetyCase!.events.filter((e) => e.kind === 'assistant_call');
    expect(steps).toEqual([{ kind: 'assistant_call', at: NOW, simulated: true, detail: 'Simulated call' }]);
  });
});

describe('urgent maps stay focused', () => {
  it('turn-around shows only confirmed flooding; check-in drops unchecked roads and gauges', () => {
    const base = reducer(initialState(NOW), { type: 'set_scenario', scenario: 'check_in', now: NOW });
    const layer = {
      at: null,
      roads: [
        { id: 'f', name: 'F', status: 'confirmed_flooded' as const, coords: [[0, 0], [1, 1]] as [number, number][] },
        { id: 'l', name: 'L', status: 'likely_flooded' as const, coords: [[0, 0], [1, 1]] as [number, number][] },
        { id: 'u', name: 'U', status: 'unknown' as const, coords: [[0, 0], [1, 1]] as [number, number][] },
      ],
      points: [],
      gauges: [{ site: 'g', name: 'G', at: [0, 0] as [number, number], stageFt: 3, category: null }],
      alerts: [],
      sample: false,
      replay: true,
    };
    const s = reducer(base, { type: 'set_flood_layer', layer });
    expect(buildScene(s, 'alert').flood.roads.map((r) => r.id)).toEqual(['f']);
    expect(buildScene(s, 'location').flood.roads.map((r) => r.id)).toEqual(['f', 'l']);
    expect(buildScene(s, 'location').flood.gauges).toEqual([]);
    expect(buildScene(s, 'flood').flood.roads.length).toBe(3);
  });
});

describe('compact directions', () => {
  it('keeps decimals intact and stops at the first sentence end', () => {
    expect(firstSentence('Head for higher ground by G Street, about 1.4 km. This way avoids known flooding.')).toBe(
      'Head for higher ground by G Street, about 1.4 km.',
    );
    expect(firstSentence('No period')).toBe('No period');
  });
});

