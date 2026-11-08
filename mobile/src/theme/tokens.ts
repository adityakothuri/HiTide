import { Platform } from 'react-native';

/** HiTide consumer palette. Royal blue and white dominate; amber and red are semantic only. */
export const color = {
  /** Cobalt, shared with the ops dashboard. White text on it is 6.6:1 (AA, AAA large). */
  primary: '#2448E8',
  primaryPressed: '#1B39C4',
  onPrimary: '#FFFFFF',
  onPrimaryMuted: '#DCE4FF',
  white: '#FFFFFF',
  ink: '#13203B',
  /** Slate secondary text: 5.2:1 on white, 4.9:1 on surface (WCAG AA). */
  secondary: '#626D85',
  /** Slightly darker than secondary for small text on pale blue (AA contrast). */
  secondaryStrong: '#5A6580',
  paleBlue: '#EEF3FF',
  paleBlueBorder: '#D9E2FB',
  surface: '#F6F8FC',
  divider: '#E6EAF2',
  amber: '#F2A516',
  amberInk: '#8A5A00',
  hazardBg: '#FFF7E8',
  hazardBorder: '#F6DDAA',
  emergency: '#C62828',
  success: '#2448E8',
  scrim: 'rgba(19, 32, 59, 0.45)',
  mapWater: '#B9D3F5',
  mapLand: '#F3F5F8',
  mapRoad: '#FFFFFF',
  mapRoadMajor: '#FFFFFF',
  mapRoadEdge: '#DDE2EA',
  mapPark: '#DCEFD9',
  routeOriginal: '#8E97A8',
} as const;

export const space = {
  xxs: 4,
  xs: 8,
  sm: 12,
  md: 16,
  lg: 20,
  xl: 24,
  xxl: 32,
  xxxl: 40,
} as const;

/** Horizontal content margin used across screens. */
export const gutter = space.xl;

export const radius = {
  panel: 18,
  control: 12,
  pill: 999,
} as const;

/** Minimum touch target (iOS 44pt, Android 48dp). */
export const touchTarget = Platform.select({ android: 48, default: 44 });

/**
 * Native type scale. One heavy weight (700) for titles only; everything else
 * is regular or semibold, so hierarchy comes from size and color, not boldness.
 */
export const font = {
  /** Urgent single instruction (turn-around). */
  alert: { fontSize: 38, lineHeight: 44, fontWeight: '700' as const, letterSpacing: -0.6 },
  largeTitle: { fontSize: 34, lineHeight: 40, fontWeight: '700' as const, letterSpacing: -0.8 },
  display: { fontSize: 32, lineHeight: 38, fontWeight: '700' as const, letterSpacing: -0.8 },
  title: { fontSize: 26, lineHeight: 31, fontWeight: '700' as const, letterSpacing: -0.5 },
  heading: { fontSize: 19, lineHeight: 24, fontWeight: '600' as const, letterSpacing: -0.2 },
  rowTitle: { fontSize: 16, lineHeight: 21, fontWeight: '600' as const, letterSpacing: -0.1 },
  body: { fontSize: 16, lineHeight: 22, fontWeight: '400' as const },
  small: { fontSize: 14, lineHeight: 19, fontWeight: '400' as const },
  caption: { fontSize: 13, lineHeight: 17, fontWeight: '400' as const },
  /** Eyebrow / section label. Sentence case, normal tracking: calm, not shouty. */
  overline: { fontSize: 13, lineHeight: 18, fontWeight: '600' as const, letterSpacing: 0 },
  tabLabel: { fontSize: 12, lineHeight: 16, fontWeight: '600' as const },
  wordmark: { fontSize: 18, lineHeight: 23, fontWeight: '600' as const, letterSpacing: -0.3 },
  buttonLarge: { fontSize: 19, lineHeight: 24, fontWeight: '600' as const, letterSpacing: -0.1 },
  button: { fontSize: 17, lineHeight: 22, fontWeight: '600' as const, letterSpacing: -0.1 },
} as const;

/** Times and counts keep their width as digits change. */
export const tabular = { fontVariant: ['tabular-nums' as const] };

/** Approximates text-wrap: balance for short headings on iOS. */
export const balanced = { lineBreakStrategyIOS: 'push-out' as const };

/** Neutral hairline for map and image edges; never tinted with the brand color. */
export const edge = 'rgba(19, 32, 59, 0.08)';

export const shadow = {
  /** Layered: a tight contact shadow plus a soft ambient one. */
  panel: Platform.select({
    ios: { boxShadow: '0 1px 2px rgba(19,32,59,0.08), 0 8px 24px rgba(19,32,59,0.08)' },
    android: { elevation: 3 },
    default: { boxShadow: '0 1px 2px rgba(19,32,59,0.08), 0 8px 24px rgba(19,32,59,0.08)' },
  }),
  control: Platform.select({
    ios: { shadowColor: '#13203B', shadowOpacity: 0.12, shadowRadius: 6, shadowOffset: { width: 0, height: 2 } },
    android: { elevation: 3 },
    default: { boxShadow: '0 2px 6px rgba(19,32,59,0.12)' },
  }),
};

/**
 * Risk severity, the same values and mapping the ops dashboard uses (frontend/src/styles/tokens.css --sev-* and
 * --d-*; region/derive.ts personTone/pointTone): critical and danger share the critical tone, warning is amber,
 * watch and below are muted.
 */
export const risk = {
  critical: '#D92D20',
  criticalInk: '#B42318',
  criticalBg: '#FDECEA',
  criticalLine: '#F4B4AE',
  warning: '#F08C00',
  warningInk: '#8A5300',
  warningBg: '#FDF3DC',
  warningLine: '#F2C46D',
  muted: '#7A8594',
} as const;

/** Flood map colours, from the dashboard's region map (severity tones) and NWS gauge categories. */
export const flood = {
  flooded: risk.critical,
  likely: risk.warning,
  /** Likely flooded on the map: thin and translucent, so dozens of short segments read as a tint, not blobs. */
  likelySoft: '#F08C0099',
  unknown: risk.muted,
  unknownSoft: '#7A859459',
  directions: '#13203B',
  gaugeMajor: '#B25FD9',
  gaugeModerate: '#E5322B',
  gaugeMinor: '#F28C28',
  gaugeAction: '#F2D43D',
  gaugeBelow: '#8B97A4',
} as const;

export const GAUGE_COLOR: Record<string, string> = {
  major: flood.gaugeMajor,
  moderate: flood.gaugeModerate,
  minor: flood.gaugeMinor,
  action: flood.gaugeAction,
};
