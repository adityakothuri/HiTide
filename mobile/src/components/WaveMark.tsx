import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { color, font } from '@/theme/tokens';

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
  tint?: string;
  /** Development-only: long-press opens scenario controls. */
  onLongPress?: () => void;
}

export function Wordmark({ tint = color.white, onLongPress }: WordmarkProps) {
  const content = (
    <View style={styles.row}>
      <WaveGlyph size={26} />
      <Text style={[styles.word, { color: tint }]} maxFontSizeMultiplier={1.4}>
        HiTide
      </Text>
    </View>
  );
  if (!onLongPress) return content;
  return (
    <Pressable onLongPress={onLongPress} delayLongPress={600} accessibilityRole="header" accessibilityLabel="HiTide">
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  badge: { backgroundColor: color.white, alignItems: 'center', justifyContent: 'center' },
  word: { ...font.heading, fontSize: 18, fontWeight: '600', letterSpacing: -0.3 },
});
