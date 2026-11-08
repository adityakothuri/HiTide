import { StyleSheet, Text, View } from 'react-native';
import type { Directions } from '@/domain/types';
import { color, font, radius, space } from '@/theme/tokens';
import { Icon } from './Icon';

interface DirectionsCardProps {
  directions: Directions;
  /** Urgent screens: the first sentence only (where to go); the full guidance is on the help and assistant screens. */
  isCompact?: boolean;
}

/** Up to the first full stop that ends a sentence ("1.4 km" is not a sentence end). */
export const firstSentence = (text: string): string => text.match(/^[\s\S]*?\.(?=\s|$)/)?.[0] ?? text;

const TITLE: Record<Directions['kind'], string> = {
  route: 'Way to higher ground',
  stay: 'Stay where you are',
  none: 'No clear way out by road',
};

/** Where to go, as text. The map draws the same way as a dark line. Never described as safe. */
export function DirectionsCard({ directions, isCompact = false }: DirectionsCardProps) {
  const text = isCompact ? firstSentence(directions.text) : directions.text;
  return (
    <View style={styles.card} accessible accessibilityLabel={`${TITLE[directions.kind]}. ${text}`}>
      <Icon name="route" size={22} color={color.ink} />
      <View style={styles.text}>
        <Text style={styles.title}>{TITLE[directions.kind]}</Text>
        <Text style={styles.body}>{text}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.control,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.divider,
    backgroundColor: color.surface,
  },
  text: { flex: 1, gap: 2 },
  title: { ...font.rowTitle, color: color.ink },
  body: { ...font.small, color: color.secondaryStrong },
});
