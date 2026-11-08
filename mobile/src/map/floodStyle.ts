import type { FloodStatus } from '@/domain/types';
import { pointTone, type RiskTone } from '@/domain/riskLevel';
import { flood, GAUGE_COLOR, risk } from '@/theme/tokens';

/** How each flood status is drawn. Colour matches the dashboard; width and dash carry the meaning too. */
export interface LineStyle {
  color: string;
  width: number;
  /** Dash pattern (on, off) in points; undefined for solid. */
  dash?: readonly [number, number];
  z: number;
}

// Confirmed flooding is the one thing that must jump out: thick, solid red. "Likely" is a thin translucent amber
// line and "not checked" a faint hairline; no dashes, which turn short road segments into blobs at town zoom.
const ROAD: Record<Exclude<FloodStatus, 'open'>, LineStyle> = {
  confirmed_flooded: { color: flood.flooded, width: 4, z: 3 },
  likely_flooded: { color: flood.likelySoft, width: 2.5, z: 2 },
  unknown: { color: flood.unknownSoft, width: 1.5, z: 1 },
};

export function roadStyle(status: FloodStatus): LineStyle | null {
  return status === 'open' ? null : ROAD[status];
}

const TONE_COLOR: Record<RiskTone, string> = { critical: risk.critical, warning: risk.warning, muted: risk.muted };

/** Crossing colour: the dashboard's pointTone, one palette for both. */
export function pointColor(status: FloodStatus): string {
  return TONE_COLOR[pointTone(status)];
}

export function gaugeColor(category: string | null): string {
  return (category && GAUGE_COLOR[category]) || flood.gaugeBelow;
}

export const STATUS_LABEL: Record<FloodStatus, string> = {
  confirmed_flooded: 'flooded',
  likely_flooded: 'likely flooded',
  unknown: 'not checked',
  open: 'no flooding reported',
};

export const DIRECTIONS_STYLE: LineStyle = { color: flood.directions, width: 3.5, z: 4 };
