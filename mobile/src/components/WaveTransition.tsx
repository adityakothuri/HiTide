import { usePathname } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { type LayoutChangeEvent, StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  ReduceMotion,
  type SharedValue,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';
import { color } from '@/theme/tokens';

/** Focused safety flows get the fuller two-layer wave. */
const FOCUSED_ROUTES = new Set(['/turn-around', '/check-in', '/support', '/resolved']);
/** Routes that only bounce elsewhere: no curtain. */
const SILENT_ROUTES = new Set(['/dev-action']);

const FULL = { durationMs: 550, amplitude: 18, wavelength: 180, lagMs: 70 } as const;
const LIGHT = { durationMs: 420, amplitude: 12, wavelength: 220, lagMs: 0 } as const;
/** How many wavelengths the crest travels sideways during one pass. */
const RIPPLE_CYCLES = 1.5;
const EASE = Easing.bezier(0.45, 0, 0.25, 1);

type Wave = typeof FULL | typeof LIGHT;

/** A closed path: sine crest on top and bottom, `width` wide (one extra wavelength for the ripple), `height` tall. */
export function wavePath(width: number, height: number, amplitude: number, wavelength: number): string {
  const step = wavelength / 8;
  const top: string[] = [];
  const bottom: string[] = [];
  for (let x = 0; x <= width + step; x += step) {
    const y = amplitude * Math.sin((2 * Math.PI * x) / wavelength);
    top.push(`${x.toFixed(1)},${(amplitude + y).toFixed(1)}`);
    bottom.push(`${x.toFixed(1)},${(height + amplitude + y).toFixed(1)}`);
  }
  return `M${top.join(' L')} L${bottom.reverse().join(' L')} Z`;
}

interface LayerProps {
  progress: SharedValue<number>;
  size: { w: number; h: number };
  wave: Wave;
  fill: string;
  /** Phase offset, so two layers don't crest together. */
  shift: number;
}

function WaveLayer({ progress, size, wave, fill, shift }: LayerProps) {
  const bodyH = size.h + wave.amplitude * 2;
  const style = useAnimatedStyle(() => {
    const p = progress.value;
    return {
      // Rises from below the screen, covers it at the midpoint, and recedes off the top.
      transform: [
        { translateY: size.h - p * (size.h + bodyH) },
        { translateX: -((p * RIPPLE_CYCLES + shift) % 1) * wave.wavelength },
      ],
    };
  });
  return (
    <Animated.View style={[styles.layer, style]}>
      <Svg width={size.w + wave.wavelength} height={bodyH}>
        <Path d={wavePath(size.w + wave.wavelength, size.h, wave.amplitude, wave.wavelength)} fill={fill} />
      </Svg>
    </Animated.View>
  );
}

/**
 * A royal-blue wave curtain over every route change. Runs on the UI thread, never takes touches, and is skipped on the
 * first mount and when Reduce Motion is on.
 */
export function WaveTransition() {
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();
  const previous = useRef<string | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [wave, setWave] = useState<Wave>(LIGHT);
  const front = useSharedValue(1);
  const back = useSharedValue(1);

  useEffect(() => {
    const was = previous.current;
    previous.current = pathname;
    if (was === null || was === pathname || reduceMotion || SILENT_ROUTES.has(pathname)) return;
    const next = FOCUSED_ROUTES.has(pathname) ? FULL : LIGHT;
    setWave(next);
    const timing = { duration: next.durationMs - next.lagMs, easing: EASE, reduceMotion: ReduceMotion.System };
    back.value = 0;
    back.value = withTiming(1, timing);
    front.value = 0;
    front.value = withDelay(next.lagMs, withTiming(1, timing), ReduceMotion.System);
  }, [pathname, reduceMotion, front, back]);

  const onLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    if (width !== size.w || height !== size.h) setSize({ w: width, h: height });
  };

  if (reduceMotion) return null;
  return (
    <View
      style={StyleSheet.absoluteFill}
      pointerEvents="none"
      onLayout={onLayout}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      {size.h > 0 ? (
        <>
          {wave === FULL ? <WaveLayer progress={back} size={size} wave={wave} fill={color.paleBlue} shift={0.35} /> : null}
          <WaveLayer progress={wave === FULL ? front : back} size={size} wave={wave} fill={color.primary} shift={0} />
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  layer: { position: 'absolute', top: 0, left: 0 },
});
