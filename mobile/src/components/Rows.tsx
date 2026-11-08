import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { balanced, color, font, radius, space, touchTarget } from '@/theme/tokens';
import { Icon, type IconName } from './Icon';

interface IconBadgeProps {
  name: IconName;
  size?: number;
  tint?: string;
  background?: string;
}

/** Filled badge, reserved for moments that need a focal point (not list rows). */
export function IconBadge({ name, size = 44, tint = color.primary, background = color.paleBlue }: IconBadgeProps) {
  return (
    <View style={[styles.badge, { width: size, height: size, borderRadius: size / 2, backgroundColor: background }]}>
      <Icon name={name} size={size * 0.5} color={tint} />
    </View>
  );
}

interface ListRowProps {
  icon: IconName;
  title: string;
  subtitle?: string;
  onPress?: () => void;
  accessibilityHint?: string;
  right?: ReactNode;
  showDivider?: boolean;
}

const ICON_COLUMN = 28;

/** Native grouped-list row: bare line icon, text, quiet chevron, divider inset to the text. */
export function ListRow({ icon, title, subtitle, onPress, accessibilityHint, right, showDivider = false }: ListRowProps) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityLabel={subtitle ? `${title}. ${subtitle}` : title}
      accessibilityHint={accessibilityHint}
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
    >
      <View style={styles.iconCol}>
        <Icon name={icon} size={22} color={color.primary} />
      </View>
      <View style={[styles.body, showDivider && styles.divider]}>
        <View style={styles.text}>
          <Text style={styles.title}>{title}</Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
        </View>
        {right ?? (onPress ? <Icon name="chevronRight" size={16} color={color.secondary} strokeWidth={2} /> : null)}
      </View>
    </Pressable>
  );
}

interface SectionHeaderProps {
  title: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function SectionHeader({ title, actionLabel, onAction }: SectionHeaderProps) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle} accessibilityRole="header">
        {title}
      </Text>
      {actionLabel && onAction ? (
        <Pressable onPress={onAction} accessibilityRole="button" hitSlop={10} style={styles.sectionAction}>
          <Text style={styles.link}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

interface PillProps {
  label: string;
  tone?: 'onBlue' | 'primary';
}

export function Pill({ label, tone = 'primary' }: PillProps) {
  const onBlue = tone === 'onBlue';
  return (
    <View style={[styles.pill, onBlue ? styles.pillOnBlue : styles.pillPrimary]}>
      <Text style={[styles.pillText, { color: onBlue ? color.white : color.primary }]} {...balanced}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { alignItems: 'center', justifyContent: 'center' },
  row: { flexDirection: 'row', alignItems: 'stretch', minHeight: touchTarget + 16 },
  pressed: { backgroundColor: color.surface },
  iconCol: { width: ICON_COLUMN + space.sm, paddingTop: 15 },
  body: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingVertical: space.sm },
  divider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: color.divider },
  text: { flex: 1, gap: 2 },
  title: { ...font.rowTitle, color: color.ink },
  subtitle: { ...font.small, color: color.secondary },
  section: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  sectionTitle: { ...font.heading, color: color.ink },
  sectionAction: { minHeight: touchTarget, justifyContent: 'center' },
  link: { ...font.body, color: color.primary },
  pill: { alignSelf: 'center', borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 4 },
  pillOnBlue: { backgroundColor: 'rgba(255,255,255,0.16)' },
  pillPrimary: { backgroundColor: color.paleBlue },
  pillText: { ...font.overline },
});
