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

/** A location the person dropped on the map: an ink pin, distinct from the blue destination pin. */
export function DropPin() {
  return (
    <View style={styles.dropPin}>
      <Svg width={34} height={44} viewBox="0 0 34 44">
        <Path d="M17 43s15-13.2 15-25.4A15 15 0 0 0 2 17.6C2 29.8 17 43 17 43z" fill={color.ink} stroke={color.white} strokeWidth={2} />
        <Path d="M17 24a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z" fill={color.white} />
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
  dropPin: { width: 34, height: 44 },
});

const FLOOD_DOT = 11;
const GAUGE_DOT = 14;

/** A low-water crossing or bridge: a diamond in its status tone, exactly as the dashboard's region map draws it. */
export function FloodDot({ fill }: { fill: string }) {
  return <View style={[floodStyles.diamond, { backgroundColor: fill }]} />;
}

/** A river gauge: a ringed circle in its NWS category colour (the dashboard's gauge markers are circles too). */
export function GaugeDot({ fill }: { fill: string }) {
  return <View style={[floodStyles.circle, { backgroundColor: fill }]} />;
}

const floodStyles = StyleSheet.create({
  diamond: {
    width: FLOOD_DOT,
    height: FLOOD_DOT,
    borderRadius: 2,
    borderWidth: 1.5,
    borderColor: color.white,
    transform: [{ rotate: '45deg' }],
  },
  circle: {
    width: GAUGE_DOT,
    height: GAUGE_DOT,
    borderRadius: GAUGE_DOT / 2,
    borderWidth: 2,
    borderColor: color.white,
  },
});
