import { type ReactNode, useEffect } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';
import Animated, {
  Easing,
  FadeIn,
  FadeInDown,
  FadeOut,
  ReduceMotion,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

/** One easing for the whole app: quick start, long gentle settle. */
export const EASE_OUT = Easing.bezier(0.2, 0.8, 0.2, 1);
const STAGGER_MS = 55;
const ENTER_MS = 420;

/** Enter: small rise + fade, staggered by index. Honors the system Reduce Motion setting. */
export function enterUp(index = 0) {
  return FadeInDown.duration(ENTER_MS).delay(index * STAGGER_MS).easing(EASE_OUT).reduceMotion(ReduceMotion.System);
}

/** Exit is shorter and quieter than enter. */
export const exitFade = FadeOut.duration(150).reduceMotion(ReduceMotion.System);
export const enterFade = FadeIn.duration(260).easing(EASE_OUT).reduceMotion(ReduceMotion.System);

interface AppearProps {
  index?: number;
  style?: StyleProp<ViewStyle>;
  children: ReactNode;
}

export function Appear({ index = 0, style, children }: AppearProps) {
  return (
    <Animated.View entering={enterUp(index)} style={style}>
      {children}
    </Animated.View>
  );
}

/** Gentle repeating nudge, e.g. the turn-around arrow. */
export function useNudge(distance = 6, period = 1400) {
  const y = useSharedValue(0);
  useEffect(() => {
    y.value = withDelay(
      400,
      withRepeat(
        withSequence(
          withTiming(-distance, { duration: period / 2, easing: Easing.inOut(Easing.quad), reduceMotion: ReduceMotion.System }),
          withTiming(0, { duration: period / 2, easing: Easing.inOut(Easing.quad), reduceMotion: ReduceMotion.System }),
        ),
        -1,
        false,
      ),
    );
  }, [y, distance, period]);
  return useAnimatedStyle(() => ({ transform: [{ translateY: y.value }] }));
}
