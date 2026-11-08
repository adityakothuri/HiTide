import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { enterFade, enterUp } from '@/components/Motion';
import { useStatusBar } from '@/components/ScreenHeader';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import type { LngLat } from '@/domain/types';
import { FloodMap } from '@/map/FloodMap';
import { buildScene } from '@/map/scene';
import { deriveFlowMode } from '@/state/reducer';
import { color, font, gutter, radius, shadow, space, tabular, touchTarget } from '@/theme/tokens';
import { formatLngLat } from './locationResultCopy';

/** Height the bottom panel covers, so the map keeps its controls and attribution above it. */
const PANEL_INSET = 236;

/** Full-screen map: tap to drop a pin, then confirm. HiTide checks that spot as if the person were stopped there. */
export function SetLocationScreen() {
  const state = useAppState();
  const repo = useRepository();
  const insets = useSafeAreaInsets();
  const [pin, setPin] = useState<LngLat | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scene = buildScene(state, 'flood');
  useStatusBar('dark');

  const drop = (p: LngLat) => {
    setError(null);
    setPin(p);
  };

  const confirm = async () => {
    if (!pin || pending) return;
    setPending(true);
    setError(null);
    const before = deriveFlowMode(repo.getSnapshot());
    try {
      await repo.setLocation(pin);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t set your location. Try again.');
      setPending(false);
      return;
    }
    const after = deriveFlowMode(repo.getSnapshot());
    if (after !== 'normal') {
      // Danger or critical: the backend opened a case and is calling. FlowGate moves to the check-in when the mode
      // changes; if it was already showing, just close this map.
      if (after === before && router.canGoBack()) router.back();
      return;
    }
    router.replace('/location-result');
  };

  return (
    <View style={styles.screen}>
      <FloodMap
        scene={scene}
        accessibilityLabel="Map of Kerrville. Tap where you are to drop a pin."
        interactive
        showControls
        rounded={false}
        bottomInset={PANEL_INSET}
        onPressCoordinate={drop}
        pin={pin}
        style={StyleSheet.absoluteFill}
      />

      <Animated.View entering={enterFade} style={[styles.topBar, { top: insets.top + space.xs }]} pointerEvents="box-none">
        <Pressable
          onPress={() => router.back()}
          accessibilityRole="button"
          accessibilityLabel="Close"
          hitSlop={6}
          style={[styles.chip, styles.close]}
        >
          <Icon name="close" size={20} color={color.ink} strokeWidth={2.2} />
        </Pressable>
        <View style={styles.chip}>
          <Text style={styles.chipText} accessibilityRole="header">
            Set your location
          </Text>
        </View>
        <View style={styles.spacer} />
      </Animated.View>

      <Animated.View
        entering={enterUp(1)}
        style={[styles.panel, shadow.panel, { paddingBottom: Math.max(insets.bottom, space.md) }]}
      >
        <View style={styles.handle} />
        <View style={styles.pinRow} accessible accessibilityLiveRegion="polite">
          <View style={styles.pinIcon}>
            <Icon name="pin" size={22} color={pin ? color.primary : color.secondary} />
          </View>
          <View style={styles.pinText}>
            <Text style={[styles.pinTitle, pin && tabular]}>{pin ? formatLngLat(pin) : 'Tap the map to drop a pin'}</Text>
            <Text style={styles.pinHelp}>
              {pin
                ? 'HiTide will check this spot for flooding. Tap elsewhere to move the pin.'
                : 'Drop it where you are. HiTide checks that spot for flooding.'}
            </Text>
          </View>
        </View>
        {pin ? null : (
          <Pressable
            onPress={() => drop([scene.region.longitude, scene.region.latitude])}
            accessibilityRole="button"
            accessibilityLabel="Drop the pin at the centre of the map"
            style={styles.centerLink}
          >
            <Text style={styles.centerLinkText}>Use the centre of the map</Text>
          </Pressable>
        )}
        {error ? (
          <Text style={styles.error} accessibilityRole="alert" accessibilityLiveRegion="assertive">
            {error}
          </Text>
        ) : null}
        <Button
          label="Confirm this location"
          icon="pinCheck"
          onPress={() => void confirm()}
          isBusy={pending}
          isDisabled={!pin}
        />
        <Button label="Cancel" variant="quiet" onPress={() => router.back()} isDisabled={pending} />
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.mapLand },
  topBar: {
    position: 'absolute',
    left: space.md,
    right: space.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  chip: {
    minHeight: touchTarget,
    justifyContent: 'center',
    paddingHorizontal: 14,
    borderRadius: radius.pill,
    backgroundColor: color.white,
    boxShadow: '0 1px 2px rgba(19,32,59,0.10), 0 4px 12px rgba(19,32,59,0.08)',
  },
  chipText: { ...font.rowTitle, color: color.ink },
  close: { width: touchTarget, paddingHorizontal: 0, alignItems: 'center' },
  spacer: { width: touchTarget },
  panel: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: color.white,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: gutter,
    paddingTop: space.xs,
    gap: space.sm,
  },
  handle: { alignSelf: 'center', width: 36, height: 5, borderRadius: 3, backgroundColor: color.divider },
  pinRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  pinIcon: {
    width: touchTarget,
    height: touchTarget,
    borderRadius: touchTarget / 2,
    backgroundColor: color.paleBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pinText: { flex: 1, gap: 2 },
  pinTitle: { ...font.rowTitle, color: color.ink },
  pinHelp: { ...font.small, color: color.secondary },
  centerLink: { minHeight: touchTarget, justifyContent: 'center', alignSelf: 'flex-start' },
  centerLinkText: { ...font.small, fontWeight: '600', color: color.primary },
  error: { ...font.small, color: color.emergency, textAlign: 'center' },
});
