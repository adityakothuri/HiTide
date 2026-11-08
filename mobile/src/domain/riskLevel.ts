import type { DangerLevel, FloodStatus } from './types';

/**
 * Risk tones, mirroring the ops dashboard (frontend/src/region/derive.ts) so the phone and the dashboard never
 * disagree about how serious something is: critical and danger share the critical tone, warning is amber, watch and
 * below are muted.
 */
export type RiskTone = 'critical' | 'warning' | 'muted';

export function levelTone(level: DangerLevel | null): RiskTone {
  if (level === 'critical' || level === 'danger') return 'critical';
  return level === 'warning' ? 'warning' : 'muted';
}

export function pointTone(status: FloodStatus): RiskTone {
  if (status === 'confirmed_flooded') return 'critical';
  return status === 'likely_flooded' ? 'warning' : 'muted';
}

/** The dashboard's labels for a person's level ("" for none). */
export const LEVEL_LABEL: Record<DangerLevel, string> = {
  critical: 'Critical',
  danger: 'Danger',
  warning: 'Warning',
  watch: 'Watch',
  none: '',
};
