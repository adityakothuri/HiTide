import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { color, font, gutter, space, touchTarget } from '@/theme/tokens';
import { Icon } from './Icon';

interface SheetScreenProps {
  title: string;
  overline?: string;
  children: ReactNode;
  footer?: ReactNode;
}

/** Layout for detail sheets presented modally over the tabs. */
export function SheetScreen({ title, overline, children, footer }: SheetScreenProps) {
  const insets = useSafeAreaInsets();
  const top = Platform.OS === 'ios' ? space.md : insets.top + space.xs;
  return (
    <View style={styles.screen}>
      <View style={[styles.header, { paddingTop: top }]}>
        <View style={{ flex: 1 }}>
          {overline ? <Text style={styles.overline}>{overline}</Text> : null}
          <Text style={styles.title} accessibilityRole="header">
            {title}
          </Text>
        </View>
        <Pressable
          onPress={() => router.back()}
          accessibilityRole="button"
          accessibilityLabel="Close"
          hitSlop={8}
          style={styles.close}
        >
          <Icon name="close" size={20} color={color.ink} strokeWidth={2.2} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
      {footer ? (
        <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, space.md) }]}>{footer}</View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.white },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.md,
    paddingHorizontal: gutter,
    paddingBottom: space.sm,
  },
  overline: { ...font.overline, color: color.secondaryStrong, marginBottom: 4 },
  title: { ...font.title, color: color.ink },
  close: {
    width: touchTarget,
    height: touchTarget,
    borderRadius: touchTarget / 2,
    backgroundColor: color.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: { paddingHorizontal: gutter, paddingBottom: space.xl, gap: space.md },
  footer: {
    paddingHorizontal: gutter,
    paddingTop: space.sm,
    gap: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.divider,
    backgroundColor: color.white,
  },
});

export const sheetText = StyleSheet.create({
  body: { ...font.body, color: color.ink },
  muted: { ...font.small, color: color.secondary },
  label: { ...font.overline, color: color.secondaryStrong },
});
