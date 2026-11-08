import { jest } from '@jest/globals';

/**
 * Reanimated 4 needs the native worklets runtime, which Jest does not have.
 * This minimal stand-in renders plain views and makes every animation a no-op,
 * so screen tests exercise behavior rather than motion.
 */
jest.mock('react-native-reanimated', () => {
  const RN = jest.requireActual<typeof import('react-native')>('react-native');
  // Chainable builder: FadeInDown.duration(..).delay(..)… returns itself.
  const builder: Record<string, unknown> = new Proxy(
    {},
    { get: (_t, key) => (key === 'then' ? undefined : () => builder) },
  );
  const passthrough = <T,>(v: T) => v;
  const Animated = {
    View: RN.View,
    Text: RN.Text,
    ScrollView: RN.ScrollView,
    Image: RN.Image,
    createAnimatedComponent: passthrough,
  };
  return {
    __esModule: true,
    default: Animated,
    ...Animated,
    useSharedValue: (v: unknown) => ({ value: v }),
    useAnimatedStyle: () => ({}),
    useAnimatedProps: () => ({}),
    useAnimatedScrollHandler: () => undefined,
    withTiming: passthrough,
    withSpring: passthrough,
    withDelay: (_d: number, v: unknown) => v,
    withRepeat: passthrough,
    withSequence: (...v: unknown[]) => v[v.length - 1],
    interpolate: () => 0,
    Extrapolation: { CLAMP: 'clamp' },
    Easing: new Proxy({}, { get: () => () => () => 0 }),
    ReduceMotion: { System: 'system', Always: 'always', Never: 'never' },
    FadeIn: builder,
    FadeOut: builder,
    FadeInDown: builder,
    ZoomIn: builder,
    LinearTransition: builder,
  };
});
