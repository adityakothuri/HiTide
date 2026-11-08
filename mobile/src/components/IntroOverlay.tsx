import { useEffect, useState } from 'react';
import { Image, StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, {
  Easing,
  ReduceMotion,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';
import { scheduleOnRN } from 'react-native-worklets';
import { color } from '@/theme/tokens';

const LOGO = require('../../assets/images/hitide-logo.png');
const TILE = 120;
const EDGE_H = 64;
const DRAIN_DELAY_MS = 1150;
const DRAIN_MS = 650;

/** Played once per app launch (module state survives remounts, not relaunches). */
let played = false;

/**
 * Opening animation, "tide out": on the splash blue, the logo pops in with two ripples, then the cover
 * drains upward with a wavy edge to reveal the app. Starts when `ready` (the native splash has hidden),
 * is skipped with Reduce Motion, and stops taking touches as soon as it starts leaving.
 */
export function IntroOverlay({ ready }: { ready: boolean }) {
  const reduce = useReducedMotion();
  const [on, setOn] = useState(() => !played);
  const [leaving, setLeaving] = useState(false);
  const { height, width } = useWindowDimensions();

  const pop = useSharedValue(0);
  const ring1 = useSharedValue(0);
  const ring2 = useSharedValue(0);
  const drain = useSharedValue(0);

  useEffect(() => {
    if (!on || !ready) return;
    played = true;
    if (reduce) return;
    const finish = () => setOn(false);
    const timing = (ms: number, delay = 0) => withDelay(delay, withTiming(1, { duration: ms, easing: Easing.out(Easing.cubic), reduceMotion: ReduceMotion.System }));
    pop.value = withSpring(1, { damping: 11, stiffness: 160, reduceMotion: ReduceMotion.System });
    ring1.value = timing(1100, 200);
    ring2.value = timing(1100, 460);
    const leave = setTimeout(() => setLeaving(true), DRAIN_DELAY_MS);
    drain.value = withDelay(
      DRAIN_DELAY_MS,
      withTiming(1, { duration: DRAIN_MS, easing: Easing.bezier(0.7, 0, 0.25, 1), reduceMotion: ReduceMotion.System }, (done) => {
        if (done) scheduleOnRN(finish);
      }),
    );
    return () => clearTimeout(leave);
  }, [on, ready, reduce, pop, ring1, ring2, drain]);

  const coverStyle = useAnimatedStyle(() => ({ transform: [{ translateY: -drain.value * (height + EDGE_H + 20) }] }));
  const tileStyle = useAnimatedStyle(() => ({
    opacity: Math.min(1, pop.value * 1.5),
    transform: [{ scale: 0.45 + pop.value * 0.55 }, { translateY: (1 - pop.value) * 14 }],
  }));
  const r1 = useAnimatedStyle(() => ({ opacity: ring1.value === 0 ? 0 : 0.7 * (1 - ring1.value), transform: [{ scale: 0.9 + ring1.value * 1.9 }] }));
  const r2 = useAnimatedStyle(() => ({ opacity: ring2.value === 0 ? 0 : 0.7 * (1 - ring2.value), transform: [{ scale: 0.9 + ring2.value * 1.9 }] }));

  // Reduce Motion: no intro at all (decided in render, not in the effect).
  if (!on || reduce) return null;
  // Waves: two periods across the screen width, dipping below the cover's bottom edge.
  const w = width;
  const wave = `M0 0 H${w} V${EDGE_H * 0.45} C ${w * 0.875} ${EDGE_H}, ${w * 0.625} ${EDGE_H}, ${w * 0.5} ${EDGE_H * 0.45} S ${w * 0.125} 0, 0 ${EDGE_H * 0.45} Z`;
  return (
    <Animated.View pointerEvents={leaving ? 'none' : 'auto'} style={[styles.cover, { height }, coverStyle]} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <View style={styles.stage}>
        <Animated.View style={[styles.ring, r1]} />
        <Animated.View style={[styles.ring, r2]} />
        <Animated.View style={[styles.tile, tileStyle]}>
          <Image source={LOGO} style={styles.logo} resizeMode="contain" />
        </Animated.View>
      </View>
      <Svg width={w} height={EDGE_H} style={styles.edge}>
        <Path d={wave} fill={color.primary} />
      </Svg>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  cover: { position: 'absolute', top: 0, left: 0, right: 0, zIndex: 1000, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  stage: { width: TILE, height: TILE, alignItems: 'center', justifyContent: 'center' },
  tile: {
    width: TILE,
    height: TILE,
    borderRadius: 28,
    backgroundColor: color.white,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.3,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 12 },
    elevation: 12,
  },
  logo: { width: TILE * 0.74, height: TILE * 0.74 },
  ring: { position: 'absolute', width: TILE, height: TILE, borderRadius: TILE / 2, borderWidth: 2, borderColor: color.white },
  edge: { position: 'absolute', top: '100%', left: 0, marginTop: -1 },
});
