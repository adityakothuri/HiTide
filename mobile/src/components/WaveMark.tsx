import { Image, Pressable, StyleSheet, View } from 'react-native';
import { color } from '@/theme/tokens';

interface WaveProps {
  size?: number;
}

const LOGO = require('../../assets/images/hitide-logo.png');

/** The HiTide logo (shield with a breaking wave) on a white badge, so it reads on the blue header. */
export function WaveGlyph({ size = 28 }: WaveProps) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      aria-hidden
      style={[styles.badge, { width: size, height: size, borderRadius: size / 4 }]}>
      <Image source={LOGO} style={{ width: size * 0.82, height: size * 0.82 }} resizeMode="contain" />
    </View>
  );
}

interface WordmarkProps {
  /** Unused since the brand became logo-only; kept so existing callers compile. */
  tint?: string;
  /** Development-only: long-press opens scenario controls. */
  onLongPress?: () => void;
}

export function Wordmark({ onLongPress }: WordmarkProps) {
  // Logo only, larger; the name is announced but not drawn.
  if (!onLongPress) {
    return (
      <View style={styles.row} accessible accessibilityRole="header" accessibilityLabel="HiTide">
        <WaveGlyph size={38} />
      </View>
    );
  }
  const content = (
    <View style={styles.row}>
      <WaveGlyph size={38} />
    </View>
  );
  return (
    <Pressable onLongPress={onLongPress} delayLongPress={600} accessibilityRole="header" accessibilityLabel="HiTide">
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  badge: { backgroundColor: color.white, alignItems: 'center', justifyContent: 'center' },
});
