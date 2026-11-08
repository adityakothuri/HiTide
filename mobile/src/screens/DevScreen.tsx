import { router } from 'expo-router';
import { useState } from 'react';
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

const DRIVE_BUTTON_MIN_WIDTH = 76;

const DRIVE_HINT = {
  idle: 'Drive the usual route; the backend decides the alerts. Tap Reset demo first for a fresh run at the flood crest.',
  preparing: 'Restarting the July 4 replay and waiting for the Kerrville crest (about a minute)…',
  driving: 'Sending location pings along the usual route…',
  stopped: 'Stopped on Park Street at Quinlan Creek.',
} as const;

/** Development-only scenario controls. Reached by long-pressing the HiTide mark. */
export function DevScreen() {
  const state = useAppState();
  const repo = useRepository();
  const drive = state.connection.drive;
  const [resetError, setResetError] = useState<string | null>(null);

  const apply = (run: () => void) => {
    if (router.canGoBack()) router.back();
    else router.replace('/');
    setTimeout(run, 60);
  };

  return (
    <SheetScreen overline="Developer" title="Scenario controls">
      {repo.supportsDemoDrive ? (
        <View style={styles.drive}>
          <View style={styles.driveTop}>
            <View style={styles.driveText}>
              <Text style={styles.tileLabel}>Demo drive</Text>
              <Text style={styles.tileHint} accessibilityLiveRegion="polite">
                {DRIVE_HINT[drive]}
              </Text>
            </View>
            <Pressable
              onPress={() => (drive === 'driving' ? repo.stopDemoDrive() : apply(() => repo.startDemoDrive()))}
              disabled={drive === 'preparing'}
              accessibilityRole="button"
              accessibilityLabel={drive === 'driving' ? 'Stop demo drive' : 'Start demo drive'}
              accessibilityState={{ disabled: drive === 'preparing', busy: drive === 'driving' }}
              style={({ pressed }) => [styles.driveButton, (pressed || drive === 'preparing') && styles.dim]}
            >
              <Text style={styles.driveButtonText}>{drive === 'driving' ? 'Stop' : 'Start'}</Text>
            </Pressable>
          </View>
          <Pressable
            onPress={() => {
              setResetError(null);
              repo.resetDemo().catch((e: unknown) => setResetError(e instanceof Error ? e.message : 'Reset failed.'));
            }}
            disabled={drive === 'preparing' || drive === 'driving'}
            accessibilityRole="button"
            accessibilityLabel="Reset demo"
            accessibilityHint="Restarts the July 4 replay for everyone, including the dashboard, and waits for the flood crest"
            accessibilityState={{ busy: drive === 'preparing' }}
            style={({ pressed }) => [styles.resetDemo, (pressed || drive === 'preparing') && styles.dim]}
          >
            <Text style={styles.resetDemoText}>{drive === 'preparing' ? 'Preparing…' : 'Reset demo'}</Text>
          </Pressable>
          {resetError ? (
            <Text style={styles.error} accessibilityLiveRegion="assertive">
              {resetError}
            </Text>
          ) : null}
        </View>
      ) : null}
      <Text style={sheetText.muted}>
        {repo.supportsDemoDrive
          ? 'Or jump to a reference state. Live updates pause until Reset.'
          : 'Jump to any reference state. Your contact and preferences are kept.'}
      </Text>
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
          <Text style={styles.tileHint}>{repo.supportsDemoDrive ? 'Clear saved data · follow live' : 'Clear saved data'}</Text>
        </Pressable>
      </View>
      <View style={styles.row}>
        <View style={{ flex: 1 }}>
          <Text style={styles.tileLabel}>Simulate network errors</Text>
          <Text style={styles.tileHint}>Route, contact, and check-in writes fail</Text>
        </View>
        <Switch
          value={state.connection.failWrites}
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
  drive: { gap: space.sm, padding: space.sm, borderRadius: radius.control, backgroundColor: color.paleBlue },
  driveTop: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  driveText: { flex: 1, gap: 2 },
  dim: { opacity: 0.6 },
  resetDemo: {
    minHeight: touchTarget,
    borderRadius: radius.control,
    borderWidth: 1.5,
    borderColor: color.primary,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.white,
  },
  resetDemoText: { ...font.rowTitle, color: color.primary },
  error: { ...font.caption, color: color.emergency },
  driveButton: {
    minHeight: touchTarget,
    minWidth: DRIVE_BUTTON_MIN_WIDTH,
    paddingHorizontal: space.md,
    borderRadius: radius.control,
    backgroundColor: color.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  driveButtonText: { ...font.rowTitle, color: color.white },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.xs },
});
