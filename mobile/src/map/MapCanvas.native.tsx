import { memo, useEffect, useMemo, useRef } from 'react';
import { Platform, StyleSheet } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';
import { color } from '@/theme/tokens';
import { toLatLng } from './geo';
import type { MapCanvasProps } from './MapCanvas';
import type { MapScene } from './scene';
import { DIRECTIONS_STYLE, gaugeColor, pointColor, roadStyle } from './floodStyle';
import { DropPin, FloodDot, GaugeDot } from './markers';
import { MarkerView, VectorMap } from './VectorMap';

const CENTER = { x: 0.5, y: 0.5 };
const BOTTOM = { x: 0.5, y: 1 };

/** Route lines: the chosen way bold; other options thin and quiet so the flood picture stays readable. */
const LINE = {
  selected: { color: color.primary, width: 3.5 },
  original: { color: color.routeOriginal, width: 3 },
  option: { color: `${color.routeOriginal}99`, width: 2 },
} as const;

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

interface OverlayProps {
  flood: MapScene['flood'];
  directions: MapScene['directions'];
}

/** Flood roads, crossings, gauges and the way to higher ground. Memoized: polls with no change don't redraw. */
const FloodOverlay = memo(function FloodOverlay({ flood, directions }: OverlayProps) {
  const roads = useMemo(
    () => flood.roads.map((r) => ({ ...r, style: roadStyle(r.status), latLng: r.coords.map(toLatLng) })),
    [flood.roads],
  );
  return (
    <>
      {roads.map((r) =>
        r.style ? (
          <Polyline
            key={`f-${r.id}-${r.status}`}
            coordinates={r.latLng}
            strokeColor={r.style.color}
            strokeWidth={r.style.width}
            lineDashPattern={r.style.dash ? [...r.style.dash] : undefined}
            lineCap="round"
            zIndex={r.style.z}
          />
        ) : null,
      )}
      {directions.map((line, i) => (
        <Polyline
          key={`d-${i}`}
          coordinates={line.map(toLatLng)}
          strokeColor={DIRECTIONS_STYLE.color}
          strokeWidth={DIRECTIONS_STYLE.width}
          lineCap="round"
          lineJoin="round"
          zIndex={DIRECTIONS_STYLE.z}
        />
      ))}
      {flood.points.map((p) => {
        const wet = p.status === 'confirmed_flooded' || p.status === 'likely_flooded';
        return (
          <Marker
            key={`p-${p.id}-${p.status}`}
            coordinate={toLatLng(p.at)}
            anchor={CENTER}
            tracksViewChanges={false}
            accessibilityLabel={wet ? p.label : undefined}
            accessibilityElementsHidden={!wet}
            zIndex={5}
          >
            <FloodDot fill={pointColor(p.status)} />
          </Marker>
        );
      })}
      {flood.gauges.map((g) => (
        <Marker key={`g-${g.id}-${g.category ?? 'none'}`} coordinate={toLatLng(g.at)} anchor={CENTER} tracksViewChanges={false} accessibilityLabel={g.label} zIndex={5}>
          <GaugeDot fill={gaugeColor(g.category)} />
        </Marker>
      ))}
    </>
  );
});

export function MapCanvas({ scene, interactive, recenterToken, satellite, bottomInset, onPressCoordinate, pin }: MapCanvasProps) {
  const ref = useRef<MapView>(null);

  useEffect(() => {
    if (recenterToken > 0) ref.current?.animateToRegion(scene.region, 450);
  }, [recenterToken, scene.region]);

  if (FORCE_VECTOR) return <VectorMap scene={scene} onPressCoordinate={onPressCoordinate} pin={pin} />;

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
      onPress={
        onPressCoordinate
          ? (e) => onPressCoordinate([e.nativeEvent.coordinate.longitude, e.nativeEvent.coordinate.latitude])
          : undefined
      }
    >
      <FloodOverlay flood={scene.flood} directions={scene.directions} />
      {scene.lines.map((l) => (
        <Polyline
          key={l.id}
          coordinates={l.coords.map(toLatLng)}
          strokeColor={LINE[l.kind].color}
          strokeWidth={LINE[l.kind].width}
          lineDashPattern={l.kind === 'original' ? [8, 8] : undefined}
          lineCap="round"
          lineJoin="round"
          zIndex={l.kind === 'selected' ? 6 : 5}
        />
      ))}
      {scene.markers.map((m) => (
        <Marker
          key={m.id}
          coordinate={toLatLng(m.at)}
          anchor={m.kind === 'destination' || m.kind === 'closure' ? { x: 0.5, y: 1 } : { x: 0.5, y: 0.5 }}
          tracksViewChanges={false}
          accessibilityLabel={m.label}
          zIndex={m.kind === 'closure' ? 7 : 8}
        >
          <MarkerView kind={m.kind} />
        </Marker>
      ))}
      {pin ? (
        <Marker
          key={`pin-${pin[0]}-${pin[1]}`}
          coordinate={toLatLng(pin)}
          anchor={BOTTOM}
          tracksViewChanges={false}
          accessibilityLabel="Your dropped pin"
          zIndex={9}
        >
          <DropPin />
        </Marker>
      ) : null}
    </MapView>
  );
}
