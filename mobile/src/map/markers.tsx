import { StyleSheet, View } from 'react-native';
import Svg, { Path, Rect } from 'react-native-svg';
import { color } from '@/theme/tokens';

export function UserDot() {
  return (
    <View style={styles.halo}>
      <View style={styles.dot} />
    </View>
  );
}

export function HeadingMarker() {
  return (
    <View style={styles.headingRing}>
      <View style={styles.heading}>
        <Svg width={18} height={18} viewBox="0 0 24 24">
          <Path d="M12 3 19 20l-7-4-7 4z" fill={color.white} />
        </Svg>
      </View>
    </View>
  );
}

export function DestinationPin() {
  return (
    <View style={styles.pin}>
      <Svg width={30} height={38} viewBox="0 0 30 38">
        <Path d="M15 37s13-11.4 13-22A13 13 0 0 0 2 15c0 10.6 13 22 13 22z" fill={color.primary} />
        <Path d="M15 21a6 6 0 1 0 0-12 6 6 0 0 0 0 12z" fill={color.white} />
      </Svg>
    </View>
  );
}

/** Road-closure barricade: amber and ink stripes, the one hazard accent on the map. */
export function ClosureMarker({ size = 34 }: { size?: number }) {
  const h = size * 0.72;
  return (
    <View accessibilityLabel="Reported road closure">
      <Svg width={size} height={h} viewBox="0 0 34 24">
        <Rect x="1" y="2" width="32" height="11" rx="2" fill={color.amber} stroke={color.ink} strokeWidth={1.5} />
        <Path d="M7 2 1 13M15 2 9 13M23 2l-6 11M31 2l-6 11" stroke={color.ink} strokeWidth={3} />
        <Path d="M6 13v10M28 13v10" stroke={color.ink} strokeWidth={2.5} strokeLinecap="round" />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  halo: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(36, 72, 232, 0.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: color.primary,
    borderWidth: 3,
    borderColor: color.white,
  },
  headingRing: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: color.white,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: color.paleBlueBorder,
  },
  heading: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: color.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pin: { width: 30, height: 38 },
});
