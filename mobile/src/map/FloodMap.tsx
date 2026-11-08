import { useState } from 'react';
import { Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { Icon } from '@/components/Icon';
import type { LngLat } from '@/domain/types';
import { color, edge, font, radius, shadow } from '@/theme/tokens';
import { MapCanvas, supportsSatellite } from './MapCanvas';
import type { MapScene } from './scene';

interface FloodMapProps {
  scene: MapScene;
  accessibilityLabel: string;
  interactive?: boolean;
  showControls?: boolean;
  /** Small "Near you" chip, as on the overview. */
  chip?: string;
  rounded?: boolean;
  bottomInset?: number;
  style?: StyleProp<ViewStyle>;
  /** Tap-to-pick (Set location): called with the tapped position. */
  onPressCoordinate?: (p: LngLat) => void;
  /** A dropped pin to draw. */
  pin?: LngLat | null;
}

export function FloodMap({
  scene,
  accessibilityLabel,
  interactive = false,
  showControls = false,
  chip,
  rounded = true,
  bottomInset = 0,
  style,
  onPressCoordinate,
  pin,
}: FloodMapProps) {
  const [recenterToken, setRecenterToken] = useState(0);
  const [satellite, setSatellite] = useState(false);

  return (
    <View
      style={[styles.frame, rounded && styles.rounded, style]}
      accessible={!interactive}
      accessibilityRole={interactive ? undefined : 'image'}
      accessibilityLabel={accessibilityLabel}
    >
      <MapCanvas
        scene={scene}
        interactive={interactive}
        recenterToken={recenterToken}
        satellite={satellite}
        bottomInset={bottomInset}
        onPressCoordinate={onPressCoordinate}
        pin={pin}
      />
      {chip ? (
        <View style={[styles.chip, shadow.control]} pointerEvents="none">
          <Icon name="pin" size={16} color={color.ink} />
          <Text style={styles.chipText}>{chip}</Text>
        </View>
      ) : null}
      {showControls ? (
        <View style={[styles.controls, { bottom: bottomInset + 12 }]}>
          {supportsSatellite ? (
            <Pressable
              onPress={() => setSatellite((s) => !s)}
              accessibilityRole="button"
              accessibilityLabel={satellite ? 'Show standard map' : 'Show satellite map'}
              accessibilityState={{ selected: satellite }}
              style={[styles.control, shadow.control]}
            >
              <Icon name="layers" size={22} color={satellite ? color.primary : color.ink} />
            </Pressable>
          ) : null}
          <Pressable
            onPress={() => setRecenterToken((t) => t + 1)}
            accessibilityRole="button"
            accessibilityLabel="Recenter map on route"
            style={[styles.control, shadow.control]}
          >
            <Icon name="locate" size={22} color={color.ink} />
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { overflow: 'hidden', backgroundColor: color.mapLand, borderWidth: StyleSheet.hairlineWidth, borderColor: edge },
  rounded: { borderRadius: radius.panel },
  chip: {
    position: 'absolute',
    left: 12,
    bottom: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: color.white,
    borderRadius: radius.pill,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  chipText: { ...font.small, color: color.ink },
  controls: { position: 'absolute', right: 12, gap: 12 },
  control: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: color.white,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
