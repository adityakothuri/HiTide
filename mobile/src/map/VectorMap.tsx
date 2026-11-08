import { useMemo, useState } from 'react';
import { type LayoutChangeEvent, Platform, StyleSheet, View } from 'react-native';
import Svg, { Polyline, Rect, Text as SvgText } from 'react-native-svg';
import { MAP_GEO } from '@/data/fixtures';
import type { LngLat } from '@/domain/types';
import { color } from '@/theme/tokens';
import { makeProjector } from './geo';
import { ClosureMarker, DestinationPin, HeadingMarker, UserDot } from './markers';
import type { MapScene } from './scene';

interface VectorMapProps {
  scene: MapScene;
}

const LABEL_FONT = Platform.select({ web: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif", default: undefined });

const MARKER_SIZE: Record<string, [number, number]> = {
  user: [40, 40],
  heading: [44, 44],
  destination: [30, 38],
  closure: [34, 25],
};

/**
 * Offline vector map drawn from the checked Kerrville fixture.
 * Used on web and whenever a native map provider is unavailable.
 */
export function VectorMap({ scene }: VectorMapProps) {
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
            {scene.lines.map((l) => (
              <Polyline
                key={l.id}
                points={drawn.pts(l.coords)}
                stroke={l.kind === 'selected' ? color.primary : color.routeOriginal}
                strokeWidth={l.kind === 'selected' ? 5 : 3.5}
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
          {scene.markers.map((m) => {
            const [x, y] = drawn.project(m.at);
            const [w, h] = MARKER_SIZE[m.kind];
            const anchorY = m.kind === 'destination' || m.kind === 'closure' ? h : h / 2;
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
        </>
      ) : null}
    </View>
  );
}

export function MarkerView({ kind }: { kind: MapScene['markers'][number]['kind'] }) {
  if (kind === 'user') return <UserDot />;
  if (kind === 'heading') return <HeadingMarker />;
  if (kind === 'destination') return <DestinationPin />;
  return <ClosureMarker />;
}

const styles = StyleSheet.create({
  marker: { position: 'absolute' },
});
