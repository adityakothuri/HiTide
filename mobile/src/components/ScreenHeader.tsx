import { useFocusEffect } from 'expo-router';
import { setStatusBarStyle, type StatusBarStyle } from 'expo-status-bar';
import { type ReactNode, useCallback } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { balanced, color, font, gutter, touchTarget } from '@/theme/tokens';
import { openDevControls } from './BlueHeader';
import { Icon } from './Icon';
import { enterFade } from './Motion';
import { Wordmark } from './WaveMark';

/** Sets the status bar for whichever screen is focused (tabs stay mounted, so mount-time styling is not enough). */
export function useStatusBar(style: StatusBarStyle) {
  useFocusEffect(
    useCallback(() => {
      setStatusBarStyle(style, true);
    }, [style]),
  );
}

interface Props {
  title?: string;
  subtitle?: string;
  onBack?: () => void;
  backLabel?: string;
  right?: ReactNode;
  /** Show the Flood Watch mark in the bar (used on focused safety screens). */
  showMark?: boolean;
}

/** Native large-title header on white. Royal blue is kept for actions, not for every header band. */
export function ScreenHeader({ title, subtitle, onBack, backLabel = 'Back', right, showMark = false }: Props) {
  const insets = useSafeAreaInsets();
  useStatusBar('dark');
  return (
    <View style={[styles.wrap, { paddingTop: insets.top + 4 }]}>
      <View style={styles.bar}>
        {onBack ? (
          <Pressable onPress={onBack} accessibilityRole="button" accessibilityLabel={backLabel} hitSlop={8} style={styles.back}>
            <Icon name="chevronLeft" size={24} color={color.primary} strokeWidth={2.2} />
            <Text style={styles.backText}>Home</Text>
          </Pressable>
        ) : showMark ? (
          <Wordmark tint={color.primary} onLongPress={openDevControls} />
        ) : (
          <View />
        )}
        {right}
      </View>
      {title ? (
        <Animated.View entering={enterFade}>
          <Text style={styles.title} accessibilityRole="header" {...balanced}>
            {title}
          </Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
        </Animated.View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: color.white, paddingHorizontal: gutter, paddingBottom: 12 },
  bar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: touchTarget },
  back: { flexDirection: 'row', alignItems: 'center', marginLeft: -8, minHeight: touchTarget, paddingRight: 8 },
  backText: { ...font.body, color: color.primary },
  title: { ...font.display, fontSize: 34, lineHeight: 40, color: color.ink, marginTop: 2 },
  subtitle: { ...font.body, color: color.secondary, marginTop: 2 },
});
