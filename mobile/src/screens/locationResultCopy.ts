import { levelTone, type RiskTone } from '@/domain/riskLevel';
import type { DangerLevel, LngLat } from '@/domain/types';

const COORD_DIGITS = 5;

/** "lat, lon" to five decimals (about a metre). */
export const formatLngLat = (p: LngLat): string => `${p[1].toFixed(COORD_DIGITS)}, ${p[0].toFixed(COORD_DIGITS)}`;

/** What the Set location result screen says for a level. Never calls a place "safe": no report is not the same as dry. */
export interface LocationResultCopy {
  tone: RiskTone;
  headline: string;
  body: string;
  /** Warning: show the way to higher ground (card and map). */
  showDirections: boolean;
  /** Whether HiTide texted the directions, for warning only. */
  textLine: string | null;
}

/** A ladder entry that sent a text, e.g. `warning -> text:warning`. */
const TEXT_SENT = /->.*\btext:/;

export function wasTexted(lastOutreach: string | null): boolean {
  return lastOutreach !== null && TEXT_SENT.test(lastOutreach);
}

export function locationResultCopy(level: DangerLevel | null, lastOutreach: string | null): LocationResultCopy {
  const tone = levelTone(level);
  if (level === 'danger' || level === 'critical') {
    return {
      tone,
      headline: 'You’re in a dangerous area.',
      body: 'HiTide is calling you now.',
      showDirections: false,
      textLine: null,
    };
  }
  if (level === 'warning') {
    return {
      tone,
      headline: 'Flooding near you',
      body: 'Go back the way you came and follow these directions.',
      showDirections: true,
      textLine: wasTexted(lastOutreach) ? 'We texted you these directions' : 'A text with these directions is on its way',
    };
  }
  return {
    tone,
    headline: 'No flooding reported where you are',
    body:
      level === 'watch'
        ? 'A flood watch is in effect. Conditions can change quickly, so avoid low-water crossings.'
        : 'Conditions can change. Never drive through floodwater.',
    showDirections: false,
    textLine: null,
  };
}
