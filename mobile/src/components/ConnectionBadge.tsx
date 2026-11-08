import { StyleSheet, Text, View } from 'react-native';
import type { Connection } from '@/domain/types';
import { formatTime } from '@/state/selectors';
import { color, font, radius, space, tabular } from '@/theme/tokens';

type Tone = 'live' | 'waiting' | 'off';

interface Status {
  label: string;
  tone: Tone;
}

/** Plain-language source of what the app is showing. Shape and text carry the meaning, not just color. */
export function connectionStatus(c: Connection): Status {
  if (c.kind === 'mock') return { label: 'Sample data', tone: 'off' };
  if (c.paused) return { label: 'Developer scenario · live updates paused', tone: 'off' };
  if (c.status === 'connecting') return { label: 'Connecting to HiTide…', tone: 'waiting' };
  if (c.status === 'offline') {
    return { label: c.assessedAt ? `Offline · last update ${formatTime(c.assessedAt)}` : 'Offline', tone: 'off' };
  }
  const when = c.assessedAt ? ` · ${formatTime(c.assessedAt)}` : '';
  return { label: c.mode === 'replay' ? `Live · July 4, 2025 replay${when}` : `Live${when}`, tone: 'live' };
}

const DOT: Record<Tone, string> = { live: color.primary, waiting: color.amber, off: color.secondary };

interface ConnectionBadgeProps {
  connection: Connection;
}

export function ConnectionBadge({ connection }: ConnectionBadgeProps) {
  const { label, tone } = connectionStatus(connection);
  return (
    <View
      style={styles.badge}
      accessible
      accessibilityRole="text"
      accessibilityLabel={`Data source: ${label}`}
      accessibilityLiveRegion="polite"
    >
      <View style={[styles.dot, { backgroundColor: DOT[tone] }, tone === 'off' && styles.dotHollow]} />
      <Text style={styles.text}>{label}</Text>
    </View>
  );
}

const DOT_SIZE = 8;

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: space.xs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xxs,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.divider,
    maxWidth: '100%',
  },
  dot: { width: DOT_SIZE, height: DOT_SIZE, borderRadius: DOT_SIZE / 2 },
  dotHollow: { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: color.secondary },
  text: { ...font.caption, ...tabular, color: color.secondaryStrong, flexShrink: 1 },
});
