import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { RouteChoice } from '@/domain/types';
import { color, flood, font, radius, risk, space, tabular, touchTarget } from '@/theme/tokens';

const METERS_PER_MILE = 1609.34;

const STATUS_COLOR: Record<RouteChoice['status'], string> = {
  flooded: flood.flooded,
  likely: flood.likely,
  clear: color.secondary,
};

/** What is known about a route's roads, in plain words. Never "safe": the best is "no flooding reported". */
export function routeStatusText(c: RouteChoice): string {
  if (c.flooded.length) return `Flooding reported on ${c.flooded.slice(0, 2).join(' and ')}`;
  if (c.likely.length) return `Likely flooding on ${c.likely.slice(0, 2).join(' and ')}`;
  return 'No flooding reported on this route';
}

interface RouteChoiceListProps {
  choices: readonly RouteChoice[];
  selectedId: string | null;
  pendingId: string | null;
  onChoose: (id: string) => void;
}

/** "Choose a route": one row per option, a single selection, status in words as well as colour. */
export function RouteChoiceList({ choices, selectedId, pendingId, onChoose }: RouteChoiceListProps) {
  return (
    <View style={styles.list} accessibilityRole="radiogroup">
      {choices.map((c) => {
        const selected = c.id === selectedId;
        const miles = (c.lengthM / METERS_PER_MILE).toFixed(1);
        const via = c.via.length ? ` · via ${c.via.join(', ')}` : '';
        const status = routeStatusText(c);
        return (
          <Pressable
            key={c.id}
            onPress={() => onChoose(c.id)}
            disabled={pendingId !== null}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected, busy: pendingId === c.id }}
            accessibilityLabel={`${c.label}. ${miles} miles, about ${c.minutes} minutes${via}. ${status}.`}
            style={({ pressed }) => [styles.row, selected && styles.rowOn, pressed && styles.pressed]}
          >
            <View style={[styles.radio, selected && styles.radioOn]}>{selected ? <View style={styles.radioDot} /> : null}</View>
            <View style={styles.text}>
              <View style={styles.top}>
                <Text style={styles.label}>{c.label}</Text>
                <Text style={styles.time}>{pendingId === c.id ? 'Checking…' : `${c.minutes} min`}</Text>
              </View>
              <Text style={styles.meta} numberOfLines={1}>
                {miles} mi{via}
              </Text>
              <View style={styles.statusRow}>
                <View style={[styles.statusDot, { backgroundColor: STATUS_COLOR[c.status] }]} />
                <Text style={[styles.status, c.status === 'flooded' && styles.statusFlooded]}>{status}</Text>
              </View>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const RADIO = 22;
const DOT = 8;

const styles = StyleSheet.create({
  list: { gap: space.xs },
  row: {
    flexDirection: 'row',
    gap: space.sm,
    minHeight: touchTarget + 20,
    padding: space.sm,
    borderRadius: radius.control,
    borderWidth: 1.5,
    borderColor: color.divider,
    backgroundColor: color.white,
  },
  rowOn: { borderColor: color.primary, backgroundColor: color.paleBlue },
  pressed: { opacity: 0.85 },
  radio: {
    width: RADIO,
    height: RADIO,
    borderRadius: RADIO / 2,
    borderWidth: 2,
    borderColor: color.secondary,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  radioOn: { borderColor: color.primary },
  radioDot: { width: RADIO / 2, height: RADIO / 2, borderRadius: RADIO / 4, backgroundColor: color.primary },
  text: { flex: 1, gap: 2 },
  top: { flexDirection: 'row', justifyContent: 'space-between', gap: space.sm },
  label: { ...font.rowTitle, color: color.ink, flexShrink: 1 },
  time: { ...font.rowTitle, ...tabular, color: color.ink },
  meta: { ...font.small, ...tabular, color: color.secondary },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs, marginTop: 2 },
  statusDot: { width: DOT, height: DOT, borderRadius: DOT / 2 },
  status: { ...font.small, color: color.secondaryStrong, flexShrink: 1 },
  statusFlooded: { color: risk.criticalInk, fontWeight: '600' },
});
