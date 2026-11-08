import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { color, font, gutter, touchTarget } from '@/theme/tokens';
import { Icon } from './Icon';
import { Wordmark } from './WaveMark';

/** Development-only entry to scenario controls: long-press the HiTide mark. */
export const openDevControls: (() => void) | undefined = __DEV__ ? () => router.push('/dev') : undefined;

interface BlueHeaderProps {
  right?: ReactNode;
  onBack?: () => void;
  backLabel?: string;
  children?: ReactNode;
  /** Extra bottom padding when a panel overlaps the header edge. */
  overlap?: number;
}

export function BlueHeader({ right, onBack, backLabel = 'Back', children, overlap = 0 }: BlueHeaderProps) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.wrap, { paddingTop: insets.top + 8, paddingBottom: 20 + overlap }]}>
      <View style={styles.bar}>
        <View style={styles.left}>
          {onBack ? (
            <Pressable
              onPress={onBack}
              accessibilityRole="button"
              accessibilityLabel={backLabel}
              hitSlop={8}
              style={styles.back}
            >
              <Icon name="chevronLeft" color={color.white} size={26} strokeWidth={2.2} />
            </Pressable>
          ) : null}
          <Wordmark onLongPress={openDevControls} />
        </View>
        {right}
      </View>
      {children ? <View style={[styles.body, onBack && styles.bodyIndented]}>{children}</View> : null}
    </View>
  );
}

interface AvatarProps {
  initials: string;
  onPress?: () => void;
}

export function Avatar({ initials, onPress }: AvatarProps) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole="button"
      accessibilityLabel="Open profile"
      hitSlop={6}
      style={({ pressed }) => [styles.avatar, pressed && { opacity: 0.85 }]}
    >
      <Text style={styles.avatarText} maxFontSizeMultiplier={1.2}>
        {initials}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: color.primary, paddingHorizontal: gutter },
  bar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: touchTarget },
  left: { flexDirection: 'row', alignItems: 'center', gap: 4, flexShrink: 1 },
  back: { width: 36, height: touchTarget, justifyContent: 'center', marginLeft: -8 },
  body: { marginTop: 10 },
  bodyIndented: { marginLeft: 28 },
  avatar: {
    width: touchTarget,
    height: touchTarget,
    borderRadius: touchTarget / 2,
    backgroundColor: color.white,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 1px 2px rgba(19,32,59,0.10), 0 4px 12px rgba(19,32,59,0.08)',
  },
  avatarText: { ...font.small, fontWeight: '600', letterSpacing: 0.4, color: color.primary },
});

export const headerText = StyleSheet.create({
  kicker: { ...font.body, color: color.onPrimaryMuted },
  title: { ...font.display, color: color.white },
  sub: { ...font.small, color: color.onPrimaryMuted },
});
