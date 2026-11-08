import { StyleSheet, Text, View } from 'react-native';
import { FloodLegend } from '@/components/FloodLegend';
import { SheetScreen, sheetText } from '@/components/SheetScreen';
import { useAppState } from '@/data/RepositoryProvider';
import { floodCounts } from '@/data/live/mapFlood';
import { FloodMap } from '@/map/FloodMap';
import { buildScene } from '@/map/scene';
import { color, font, radius, risk, space } from '@/theme/tokens';

const MAP_HEIGHT = 380;

/** The flood picture around Kerrville: the same layers the operations dashboard shows. */
export function FloodMapScreen() {
  const state = useAppState();
  const layer = state.floodLayer;
  const counts = layer ? floodCounts(layer) : null;
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const summary = counts
    ? `${plural(counts.flooded, 'road', 'roads')} flooded, ${counts.likely} likely, ${plural(counts.crossingsFlooded, 'crossing', 'crossings')} with water`
    : 'Waiting for the flood picture…';

  return (
    <SheetScreen overline="Kerrville and the Guadalupe River" title="Flood map">
      <Text style={styles.summary} accessibilityLiveRegion="polite">
        {summary}
      </Text>
      <FloodMap
        scene={buildScene(state, 'flood')}
        accessibilityLabel={`Flood map of Kerrville. ${summary}`}
        interactive
        showControls
        style={styles.map}
      />
      <FloodLegend layer={layer} />
      {layer && layer.alerts.length > 0 ? (
        <View style={styles.alerts}>
          <Text style={sheetText.label}>ACTIVE ALERTS</Text>
          {layer.alerts.map((a) => (
            <Text key={a} style={[styles.alert, /emergency/i.test(a) && styles.alertEmergency]}>
              {a}
            </Text>
          ))}
        </View>
      ) : null}
      <Text style={sheetText.muted}>
        Faint grey roads have no recent check: unknown is not the same as clear. Never drive through water.
      </Text>
    </SheetScreen>
  );
}

const styles = StyleSheet.create({
  summary: { ...font.rowTitle, color: color.ink },
  map: { height: MAP_HEIGHT, borderRadius: radius.panel },
  alerts: { gap: space.xxs },
  alert: { ...font.body, color: color.amberInk },
  alertEmergency: { color: risk.criticalInk, fontWeight: '600' },
});
