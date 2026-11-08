import type { ReactNode } from 'react';
import { StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, { Extrapolation, interpolate, useAnimatedScrollHandler, useAnimatedStyle, useSharedValue } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { FloodMap } from '@/map/FloodMap';
import type { MapScene } from '@/map/scene';
import { color, gutter, radius, space, touchTarget } from '@/theme/tokens';

export const SHEET_OVERLAP = 28;
const HERO_ACTION_GAP = 12;
const HERO_MIN = 260;
const HERO_MAX = 420;
const HERO_RATIO = 0.42;

interface HeroMapScreenProps {
  scene: MapScene;
  /** Spoken description of the hero map. */
  mapLabel: string;
  /** Floats over the top of the map (brand chip, back chip, avatar). */
  topBar: ReactNode;
  /** Pills in the row at the bottom of the hero (e.g. Flood map). */
  heroActions?: ReactNode;
  /** Sheet content. */
  children: ReactNode;
}

/**
 * A full-bleed map hero with a white sheet scrolling over it. The map drifts at half speed (parallax) and is not
 * interactive here; the hero actions open the full maps.
 */
export function HeroMapScreen({ scene, mapLabel, topBar, heroActions, children }: HeroMapScreenProps) {
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const heroH = Math.round(Math.min(Math.max(height * HERO_RATIO, HERO_MIN), HERO_MAX));

  const scrollY = useSharedValue(0);
  const onScroll = useAnimatedScrollHandler((e) => {
    scrollY.value = e.contentOffset.y;
  });
  const heroStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: interpolate(scrollY.value, [-100, 0, heroH], [0, 0, -heroH / 2], Extrapolation.CLAMP) }],
  }));

  return (
    <View style={styles.screen}>
      <Animated.View style={[styles.hero, { height: heroH }, heroStyle]}>
        <FloodMap
          scene={scene}
          accessibilityLabel={mapLabel}
          rounded={false}
          bottomInset={SHEET_OVERLAP + 8}
          style={StyleSheet.absoluteFill}
        />
      </Animated.View>

      <View style={[styles.topBar, { top: insets.top + 6 }]} pointerEvents="box-none">
        {topBar}
      </View>

      <Animated.ScrollView onScroll={onScroll} scrollEventThrottle={16} showsVerticalScrollIndicator={false}>
        {/* Sits over the map's lower edge and scrolls away with the sheet. */}
        <View style={[styles.actionRow, { height: heroH - SHEET_OVERLAP }]} pointerEvents="box-none">
          {heroActions}
        </View>
        <View style={styles.sheet}>
          <View style={styles.handle} />
          {children}
        </View>
      </Animated.ScrollView>
    </View>
  );
}

/** Translucent white pill used on the hero (brand chip, back chip, map actions). */
export const heroChip = StyleSheet.create({
  chip: {
    minHeight: touchTarget,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    paddingHorizontal: 14,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(255,255,255,0.94)',
    boxShadow: '0 1px 2px rgba(19,32,59,0.10), 0 4px 12px rgba(19,32,59,0.08)',
  },
});

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.white },
  hero: { position: 'absolute', top: 0, left: 0, right: 0 },
  actionRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'flex-end',
    gap: space.xs,
    paddingRight: space.md,
    paddingBottom: HERO_ACTION_GAP,
  },
  topBar: {
    position: 'absolute',
    left: space.md,
    right: space.md,
    zIndex: 2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sheet: {
    minHeight: 640,
    backgroundColor: color.white,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: gutter,
    paddingBottom: space.xxl,
    gap: space.md,
    boxShadow: '0 -1px 0 rgba(19,32,59,0.06), 0 -8px 24px rgba(19,32,59,0.06)',
  },
  handle: { alignSelf: 'center', width: 36, height: 5, borderRadius: 3, backgroundColor: color.divider, marginTop: 8 },
});
