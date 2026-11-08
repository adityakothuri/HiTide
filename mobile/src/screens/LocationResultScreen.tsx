import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { Button } from '@/components/Button';
import { DirectionsCard } from '@/components/DirectionsCard';
import { Icon } from '@/components/Icon';
import { Appear } from '@/components/Motion';
import { SheetScreen, sheetText } from '@/components/SheetScreen';
import { useAppState } from '@/data/RepositoryProvider';
import type { RiskTone } from '@/domain/riskLevel';
import { FloodMap } from '@/map/FloodMap';
import { buildScene } from '@/map/scene';
import { color, font, radius, risk, space } from '@/theme/tokens';
import { formatLngLat, locationResultCopy } from './locationResultCopy';

const TONE: Record<RiskTone, { bg: string; line: string; ink: string }> = {
  critical: { bg: risk.criticalBg, line: risk.criticalLine, ink: risk.criticalInk },
  warning: { bg: risk.warningBg, line: risk.warningLine, ink: risk.warningInk },
  muted: { bg: color.paleBlue, line: color.paleBlueBorder, ink: color.primary },
};

/** What HiTide found at the location the person set on the map. */
export function LocationResultScreen() {
  const state = useAppState();
  const copy = locationResultCopy(state.connection.level, state.connection.lastOutreach);
  const tone = TONE[copy.tone];
  const pin = state.lastPin;

  return (
    <SheetScreen
      overline="Your location"
      title={copy.headline}
      footer={<Button label="Done" onPress={() => router.back()} />}
    >
      <Appear index={0}>
        <View
          style={[styles.banner, { backgroundColor: tone.bg, borderColor: tone.line }]}
          accessible
          accessibilityRole="alert"
          accessibilityLabel={`${copy.headline}. ${copy.body}`}
        >
          <Icon name={copy.tone === 'muted' ? 'info' : 'warning'} size={22} color={tone.ink} strokeWidth={2} />
          <View style={styles.bannerText}>
            <Text style={[styles.bannerBody, { color: tone.ink }]}>{copy.body}</Text>
            {pin ? <Text style={styles.coords}>Pin at {formatLngLat(pin.at)}</Text> : null}
          </View>
        </View>
      </Appear>

      {copy.showDirections ? (
        <Appear index={1} style={styles.block}>
          {state.directions ? (
            <DirectionsCard directions={state.directions} />
          ) : (
            <Text style={sheetText.muted} accessibilityLiveRegion="polite">
              Finding a way to higher ground…
            </Text>
          )}
          <FloodMap
            scene={buildScene(state, 'location')}
            accessibilityLabel="Map of the location you set, with the way to higher ground"
            style={styles.map}
          />
          {copy.textLine ? (
            <View style={styles.textLine} accessible accessibilityLabel={copy.textLine}>
              <Icon name="chatCheck" size={18} color={color.primary} />
              <Text style={styles.textLineText}>{copy.textLine}</Text>
            </View>
          ) : null}
        </Appear>
      ) : null}

      <Text style={sheetText.muted}>Never drive through floodwater. Turn around, don’t drown.</Text>
    </SheetScreen>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.control + 2,
    borderWidth: StyleSheet.hairlineWidth,
  },
  bannerText: { flex: 1, gap: 2 },
  bannerBody: { ...font.rowTitle },
  coords: { ...font.caption, color: color.secondaryStrong },
  block: { gap: space.sm },
  map: { height: 200 },
  textLine: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  textLineText: { ...font.small, color: color.ink },
});
