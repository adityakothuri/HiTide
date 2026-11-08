import { Pressable, StyleSheet, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { color, font } from '@/theme/tokens';

interface WaveProps {
  size?: number;
  tint?: string;
}

/** The canonical Flood Watch mark: two stacked waves. */
export function WaveGlyph({ size = 28, tint = color.white }: WaveProps) {
  const w = size;
  const h = size * 0.6;
  return (
    <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants" aria-hidden>
      <Svg width={w} height={h} viewBox="0 0 40 24">
      <Path
        d="M3 9.5c4.2-4.6 8.4-4.6 12.6 0s8.4 4.6 12.6 0 6.3-3.4 8.8-1.3"
        stroke={tint}
        strokeWidth={3.4}
        strokeLinecap="round"
        fill="none"
      />
      <Path
        d="M3 17.5c4.2-4.6 8.4-4.6 12.6 0s8.4 4.6 12.6 0 6.3-3.4 8.8-1.3"
        stroke={tint}
        strokeWidth={3.4}
        strokeLinecap="round"
        fill="none"
      />
    </Svg>
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
      <WaveGlyph tint={tint} size={24} />
      <Text style={[styles.word, { color: tint }]} maxFontSizeMultiplier={1.4}>
        Flood Watch
      </Text>
    </View>
  );
  if (!onLongPress) return content;
  return (
    <Pressable onLongPress={onLongPress} delayLongPress={600} accessibilityRole="header" accessibilityLabel="Flood Watch">
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  word: { ...font.heading, fontSize: 18, fontWeight: '600', letterSpacing: -0.3 },
});
