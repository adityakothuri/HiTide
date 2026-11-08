import { useMemo, useState } from 'react';
import { type GestureResponderEvent, type LayoutChangeEvent, Platform, StyleSheet, View } from 'react-native';
import Svg, { Polyline, Rect, Text as SvgText } from 'react-native-svg';
import { MAP_GEO } from '@/data/fixtures';
import type { LngLat } from '@/domain/types';
import { color } from '@/theme/tokens';
import { makeProjector, unproject } from './geo';
import { DIRECTIONS_STYLE, gaugeColor, pointColor, roadStyle } from './floodStyle';
import { ClosureMarker, DestinationPin, DropPin, FloodDot, GaugeDot, HeadingMarker, UserDot } from './markers';
import type { MapScene } from './scene';

const DOT = 14;

interface VectorMapProps {
  scene: MapScene;
  onPressCoordinate?: (p: LngLat) => void;
  pin?: LngLat | null;
}

const LABEL_FONT = Platform.select({ web: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif", default: undefined });

const MARKER_SIZE: Record<string, [number, number]> = {
  user: [40, 40],
  heading: [44, 44],
  destination: [30, 38],
  closure: [34, 25],
  pin: [34, 44],
};

/** Anchored at the bottom point rather than the centre. */
const BOTTOM_ANCHORED = new Set<string>(['destination', 'closure', 'pin']);

/**
 * Offline vector map drawn from the checked Kerrville fixture.
 * Used on web and whenever a native map provider is unavailable.
 */
export function VectorMap({ scene, onPressCoordinate, pin }: VectorMapProps) {
  const [size, setSize] = useState({ w: 0, h: 0 });
  const onLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    if (width !== size.w || height !== size.h) setSize({ w: width, h: height });
  };

  const drawn = useMemo(() => {
    if (!size.w || !size.h) return null;
    const project = makeProjector(scene.region, size.w, size.h);
    const pts = (coords: readonly LngLat[]) => coords.map((c) => project(c).join(',')).join(' ');
    const zoom = 0.045 / scene.region.latitudeDelta;
    return { project, pts, zoom };
  }, [scene.region, size.w, size.h]);

  // The tap layer has no children, so locationX/Y are relative to the map itself.
  const onTap = (e: GestureResponderEvent) => {
    if (!onPressCoordinate || !size.w || !size.h) return;
    const { locationX, locationY } = e.nativeEvent;
    onPressCoordinate(unproject(scene.region, size.w, size.h, [locationX, locationY]));
  };

  return (
    <View style={StyleSheet.absoluteFill} onLayout={onLayout}>
      {drawn ? (
        <>
          <Svg width={size.w} height={size.h}>
            <Rect x={0} y={0} width={size.w} height={size.h} fill={color.mapLand} />
            {MAP_GEO.river.map((line, i) => (
              <Polyline
                key={`r${i}`}
                points={drawn.pts(line)}
                stroke={color.mapWater}
                strokeWidth={Math.min(10 * Math.sqrt(drawn.zoom), 46)}
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
              />
            ))}
            {MAP_GEO.roads.map((r, i) => (
              <Polyline
                key={`e${i}`}
                points={drawn.pts(r.coords)}
                stroke={color.mapRoadEdge}
                strokeWidth={(r.major ? 5 : 2.6) * Math.min(Math.sqrt(drawn.zoom), 2.2)}
                strokeLinecap="round"
                fill="none"
              />
            ))}
            {MAP_GEO.roads.map((r, i) => (
              <Polyline
                key={`w${i}`}
                points={drawn.pts(r.coords)}
                stroke={color.mapRoad}
                strokeWidth={(r.major ? 3.4 : 1.4) * Math.min(Math.sqrt(drawn.zoom), 2.2)}
                strokeLinecap="round"
                fill="none"
              />
            ))}
            {scene.flood.roads.map((r) => {
              const st = roadStyle(r.status);
              return st ? (
                <Polyline
                  key={`f-${r.id}`}
                  points={drawn.pts(r.coords)}
                  stroke={st.color}
                  strokeWidth={st.width}
                  strokeDasharray={st.dash ? st.dash.join(' ') : undefined}
                  strokeLinecap="round"
                  fill="none"
                />
              ) : null;
            })}
            {scene.directions.map((line, i) => (
              <Polyline
                key={`d-${i}`}
                points={drawn.pts(line)}
                stroke={DIRECTIONS_STYLE.color}
                strokeWidth={DIRECTIONS_STYLE.width}
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
              />
            ))}
            {scene.lines.map((l) => (
              <Polyline
                key={l.id}
                points={drawn.pts(l.coords)}
                stroke={l.kind === 'selected' ? color.primary : l.kind === 'option' ? `${color.routeOriginal}99` : color.routeOriginal}
                strokeWidth={l.kind === 'selected' ? 3.5 : l.kind === 'option' ? 2 : 3}
                strokeDasharray={l.kind === 'original' ? '6 6' : undefined}
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
              />
            ))}
            {scene.labels.map((lab) => {
              const [x, y] = drawn.project(lab.at);
              const town = lab.kind === 'town';
              return (
                <SvgText
                  key={lab.text}
                  x={x}
                  y={y}
                  fontSize={town ? 22 : 12}
                  fontWeight={town ? '600' : '500'}
                  fontStyle={lab.kind === 'water' ? 'italic' : 'normal'}
                  fill={lab.kind === 'water' ? color.primary : color.ink}
                  opacity={town ? 0.85 : 0.7}
                  textAnchor="middle"
                  fontFamily={LABEL_FONT}
                >
                  {lab.text}
                </SvgText>
              );
            })}
          </Svg>
          {scene.flood.points.map((p) => {
            const [x, y] = drawn.project(p.at);
            return (
              <View key={`p-${p.id}`} accessible accessibilityLabel={p.label} style={[styles.marker, { left: x - DOT / 2, top: y - DOT / 2 }]}>
                <FloodDot fill={pointColor(p.status)} />
              </View>
            );
          })}
          {scene.flood.gauges.map((g) => {
            const [x, y] = drawn.project(g.at);
            return (
              <View key={`g-${g.id}`} accessible accessibilityLabel={g.label} style={[styles.marker, { left: x - DOT / 2, top: y - DOT / 2 }]}>
                <GaugeDot fill={gaugeColor(g.category)} />
              </View>
            );
          })}
          {scene.markers.map((m) => {
            const [x, y] = drawn.project(m.at);
            const [w, h] = MARKER_SIZE[m.kind];
            const anchorY = BOTTOM_ANCHORED.has(m.kind) ? h : h / 2;
            return (
              <View
                key={m.id}
                accessible
                accessibilityLabel={m.label}
                style={[styles.marker, { left: x - w / 2, top: y - anchorY }]}
              >
                <MarkerView kind={m.kind} />
              </View>
            );
          })}
          {onPressCoordinate ? (
            <View
              style={StyleSheet.absoluteFill}
              onStartShouldSetResponder={() => true}
              onResponderRelease={onTap}
              accessibilityLabel="Map. Tap to drop a pin"
            />
          ) : null}
          {pin
            ? (() => {
                const [x, y] = drawn.project(pin);
                const [w, h] = MARKER_SIZE.pin;
                return (
                  <View
                    accessible
                    accessibilityLabel="Your dropped pin"
                    pointerEvents="none"
                    style={[styles.marker, { left: x - w / 2, top: y - h }]}
                  >
                    <DropPin />
                  </View>
                );
              })()
            : null}
        </>
      ) : null}
    </View>
  );
}

export function MarkerView({ kind }: { kind: MapScene['markers'][number]['kind'] }) {
  if (kind === 'user') return <UserDot />;
  if (kind === 'heading') return <HeadingMarker />;
  if (kind === 'destination') return <DestinationPin />;
  if (kind === 'pin') return <DropPin />;
  return <ClosureMarker />;
}

const styles = StyleSheet.create({
  marker: { position: 'absolute' },
});
