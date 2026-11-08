import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { PressableScale } from './PressableScale';
import { color, font, radius, touchTarget } from '@/theme/tokens';
import { Icon, type IconName } from './Icon';

type Variant = 'primary' | 'outline' | 'onBlue' | 'quiet';

interface ButtonProps {
  label: string;
  onPress: () => void;
  variant?: Variant;
  icon?: IconName;
  isBusy?: boolean;
  isDisabled?: boolean;
  /** Taller buttons for urgent, glanceable decisions. */
  isLarge?: boolean;
  accessibilityHint?: string;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  icon,
  isBusy = false,
  isDisabled = false,
  isLarge = false,
  accessibilityHint,
}: ButtonProps) {
  const v = VARIANTS[variant];
  const inactive = isDisabled || isBusy;
  return (
    <PressableScale
      onPress={onPress}
      disabled={inactive}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: inactive, busy: isBusy }}
      style={({ pressed }) => [
        styles.base,
        isLarge && styles.large,
        v.container,
        pressed && !inactive && v.pressed,
        isDisabled && styles.disabled,
      ]}
    >
      {isBusy ? (
        <ActivityIndicator color={v.text.color} />
      ) : (
        <View style={styles.content}>
          {icon ? <Icon name={icon} size={20} color={v.text.color} strokeWidth={2} /> : null}
          <Text style={[styles.label, isLarge && styles.largeLabel, v.text]}>{label}</Text>
        </View>
      )}
    </PressableScale>
  );
}

interface EmergencyCallLinkProps {
  onPress: () => void;
}

/** Dark-red emergency affordance. The demo shows a confirmation sheet; it never dials. */
export function EmergencyCallLink({ onPress }: EmergencyCallLinkProps) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel="Call 911"
      accessibilityHint="Opens a confirmation. This prototype does not place calls."
      hitSlop={8}
      style={({ pressed }) => [styles.callLink, pressed && { opacity: 0.6 }]}
    >
      <Icon name="phone" size={18} color={color.emergency} />
      <Text style={styles.callText}>Call 911</Text>
    </Pressable>
  );
}

const VARIANTS = {
  primary: StyleSheet.create({
    container: { backgroundColor: color.primary },
    pressed: { backgroundColor: color.primaryPressed },
    text: { color: color.white },
  }),
  outline: StyleSheet.create({
    container: { backgroundColor: color.white, borderWidth: 2, borderColor: color.primary },
    pressed: { backgroundColor: color.paleBlue },
    text: { color: color.primary },
  }),
  onBlue: StyleSheet.create({
    container: { backgroundColor: color.white },
    pressed: { backgroundColor: color.paleBlue },
    text: { color: color.primary },
  }),
  quiet: StyleSheet.create({
    container: { backgroundColor: color.paleBlue },
    pressed: { backgroundColor: color.paleBlueBorder },
    text: { color: color.primary },
  }),
};

const styles = StyleSheet.create({
  base: {
    minHeight: Math.max(touchTarget, 52),
    borderRadius: radius.control,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
  },
  large: { minHeight: 60 },
  content: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  label: { ...font.button, textAlign: 'center' },
  largeLabel: { fontSize: font.buttonLarge.fontSize, lineHeight: font.buttonLarge.lineHeight },
  disabled: { opacity: 0.5 },
  callLink: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'center',
    gap: 8,
    minHeight: touchTarget,
    paddingHorizontal: 12,
  },
  callText: { ...font.button, color: color.emergency },
});
