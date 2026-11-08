import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Pressable, type PressableProps, type StyleProp, type ViewStyle } from 'react-native';

type Props = Omit<PressableProps, 'style'> & {
  style?: StyleProp<ViewStyle> | ((state: { pressed: boolean }) => StyleProp<ViewStyle>);
  /** Scale while pressed. Large surfaces should move less than buttons. */
  pressedScale?: number;
};

const PRESS_IN_MS = 90;

function useReduceMotion(): boolean {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    let active = true;
    AccessibilityInfo.isReduceMotionEnabled().then((v) => active && setReduce(v)).catch(() => undefined);
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduce);
    return () => {
      active = false;
      sub.remove();
    };
  }, []);
  return reduce;
}

/** Pressable with a short, interruptible scale-down. Disabled when Reduce Motion is on. */
export function PressableScale({ style, pressedScale = 0.97, onPressIn, onPressOut, children, ...rest }: Props) {
  const scale = useRef(new Animated.Value(1)).current;
  const reduce = useReduceMotion();
  const to = (value: number, ms: number) =>
    Animated.timing(scale, { toValue: value, duration: ms, useNativeDriver: true }).start();

  return (
    <Pressable
      {...rest}
      onPressIn={(e) => {
        if (!reduce) to(pressedScale, PRESS_IN_MS);
        onPressIn?.(e);
      }}
      onPressOut={(e) => {
        if (!reduce) Animated.spring(scale, { toValue: 1, useNativeDriver: true, speed: 40, bounciness: 0 }).start();
        onPressOut?.(e);
      }}
    >
      {(state) => (
        <Animated.View style={[typeof style === 'function' ? style(state) : style, { transform: [{ scale }] }]}>
          {typeof children === 'function' ? children(state) : children}
        </Animated.View>
      )}
    </Pressable>
  );
}
