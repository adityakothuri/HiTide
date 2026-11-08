import { router } from 'expo-router';
import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import { SheetScreen, sheetText } from '@/components/SheetScreen';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import type { Scenario } from '@/domain/types';
import { color, font, radius, space, touchTarget } from '@/theme/tokens';

const SCENARIOS: { id: Scenario; label: string; hint: string }[] = [
  { id: 'normal', label: 'Normal', hint: 'No warnings' },
  { id: 'flood_warning', label: 'Flood warning', hint: 'Warning + route update' },
  { id: 'alternate_route', label: 'Alternate route', hint: 'Alternate selected' },
  { id: 'turn_around', label: 'Turn-around', hint: 'Urgent voice alert' },
  { id: 'check_in', label: 'Check-in', hint: 'Simulated stop' },
  { id: 'help_requested', label: 'Help requested', hint: 'Support status' },
  { id: 'resolved', label: 'Resolved', hint: 'Marked safe' },
];

/** Development-only scenario controls. Reached by long-pressing the HiTide mark. */
export function DevScreen() {
  const state = useAppState();
  const repo = useRepository();

  const apply = (run: () => void) => {
    router.back();
    setTimeout(run, 60);
  };

  return (
    <SheetScreen overline="Developer" title="Scenario controls">
      <Text style={sheetText.muted}>Jump to any reference state. Your contact and preferences are kept.</Text>
      <View style={styles.grid}>
        {SCENARIOS.map((s) => {
          const active = state.scenario === s.id;
          return (
            <Pressable
              key={s.id}
              onPress={() => apply(() => repo.setScenario(s.id))}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              style={({ pressed }) => [styles.tile, active && styles.tileOn, pressed && { opacity: 0.7 }]}
            >
              <Text style={[styles.tileLabel, active && { color: color.primary }]}>{s.label}</Text>
              <Text style={styles.tileHint}>{s.hint}</Text>
            </Pressable>
          );
        })}
        <Pressable
          onPress={() => apply(() => void repo.reset())}
          accessibilityRole="button"
          accessibilityHint="Clears saved preferences, contact edits, and read state"
          style={({ pressed }) => [styles.tile, styles.reset, pressed && { opacity: 0.7 }]}
        >
          <Text style={[styles.tileLabel, { color: color.emergency }]}>Reset</Text>
          <Text style={styles.tileHint}>Clear saved data</Text>
        </Pressable>
      </View>
      <View style={styles.row}>
        <View style={{ flex: 1 }}>
          <Text style={styles.tileLabel}>Simulate network errors</Text>
          <Text style={styles.tileHint}>Route, contact, and check-in writes fail</Text>
        </View>
        <Switch
          value={repo.simulateFailures}
          onValueChange={(v) => repo.setSimulateFailures(v)}
          accessibilityLabel="Simulate network errors"
          trackColor={{ true: color.primary, false: color.divider }}
        />
      </View>
    </SheetScreen>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  tile: {
    flexBasis: '47%',
    flexGrow: 1,
    minHeight: touchTarget + 20,
    borderRadius: radius.control,
    borderWidth: 1.5,
    borderColor: color.divider,
    padding: space.sm,
    justifyContent: 'center',
  },
  tileOn: { borderColor: color.primary, backgroundColor: color.paleBlue },
  reset: { borderColor: '#F1C9C9' },
  tileLabel: { ...font.rowTitle, color: color.ink },
  tileHint: { ...font.caption, color: color.secondary },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.xs },
});
