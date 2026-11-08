import { useEffect, useRef } from 'react';
import { Platform, StyleSheet } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';
import { color } from '@/theme/tokens';
import { toLatLng } from './geo';
import type { MapCanvasProps } from './MapCanvas';
import { MarkerView, VectorMap } from './VectorMap';

/** Force the offline vector map (e.g. Android release builds without a Google Maps key). */
const FORCE_VECTOR = process.env.EXPO_PUBLIC_MAP_MODE === 'vector';

export const supportsSatellite = !FORCE_VECTOR;

const ANDROID_LIGHT_STYLE = [
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#F3F5F8' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#B9D3F5' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#FFFFFF' }] },
  { featureType: 'road', elementType: 'labels.text.fill', stylers: [{ color: '#6D7890' }] },
];

export function MapCanvas({ scene, interactive, recenterToken, satellite, bottomInset }: MapCanvasProps) {
  const ref = useRef<MapView>(null);

  useEffect(() => {
    if (recenterToken > 0) ref.current?.animateToRegion(scene.region, 450);
  }, [recenterToken, scene.region]);

  if (FORCE_VECTOR) return <VectorMap scene={scene} />;

  return (
    <MapView
      ref={ref}
      style={StyleSheet.absoluteFill}
      initialRegion={scene.region}
      mapPadding={{ top: 0, left: 0, right: 0, bottom: bottomInset }}
      mapType={satellite ? 'hybrid' : Platform.OS === 'ios' ? 'mutedStandard' : 'standard'}
      customMapStyle={Platform.OS === 'android' ? ANDROID_LIGHT_STYLE : undefined}
      showsPointsOfInterests={false}
      showsBuildings={false}
      showsTraffic={false}
      showsCompass={false}
      toolbarEnabled={false}
      pitchEnabled={false}
      rotateEnabled={false}
      scrollEnabled={interactive}
      zoomEnabled={interactive}
      pointerEvents={interactive ? 'auto' : 'none'}
      accessibilityElementsHidden={!interactive}
    >
      {scene.lines.map((l) => (
        <Polyline
          key={l.id}
          coordinates={l.coords.map(toLatLng)}
          strokeColor={l.kind === 'selected' ? color.primary : color.routeOriginal}
          strokeWidth={l.kind === 'selected' ? 5 : 4}
          lineDashPattern={l.kind === 'original' ? [8, 8] : undefined}
          lineCap="round"
          lineJoin="round"
          zIndex={l.kind === 'selected' ? 2 : 1}
        />
      ))}
      {scene.markers.map((m) => (
        <Marker
          key={m.id}
          coordinate={toLatLng(m.at)}
          anchor={m.kind === 'destination' || m.kind === 'closure' ? { x: 0.5, y: 1 } : { x: 0.5, y: 0.5 }}
          tracksViewChanges={false}
          accessibilityLabel={m.label}
          zIndex={m.kind === 'closure' ? 3 : 4}
        >
          <MarkerView kind={m.kind} />
        </Marker>
      ))}
    </MapView>
  );
}
