import { useEffect, useState } from 'react';
import { type LayoutChangeEvent, StyleSheet, Text, View } from 'react-native';
import Animated, { ReduceMotion, useAnimatedProps, useSharedValue, withTiming } from 'react-native-reanimated';
import Svg, { Circle, Line, Path } from 'react-native-svg';
import type { GaugeReading } from '@/domain/types';
import { formatTime } from '@/state/selectors';
import { color, font, radius, space, tabular } from '@/theme/tokens';
import { EASE_OUT } from './Motion';

const AnimatedPath = Animated.createAnimatedComponent(Path);
const CHART_H = 56;
const DRAW_MS = 900;
const HEADROOM_FT = 1.5;

/** River stage for the last hours, with the action stage marked. Draws in once on mount. */
export function GaugeCard({ gauge }: { gauge: GaugeReading }) {
  const [width, setWidth] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setWidth(Math.round(e.nativeEvent.layout.width));
  const hours = gauge.series.length - 1;
  const max = Math.max(gauge.actionStageFt, ...gauge.series) + HEADROOM_FT;
  const min = Math.max(0, Math.min(...gauge.series) - HEADROOM_FT);
  const x = (i: number) => (i / hours) * width;
  const y = (v: number) => CHART_H - ((v - min) / (max - min)) * CHART_H;
  const line = gauge.series.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const length = width * 1.4;

  const progress = useSharedValue(0);
  useEffect(() => {
    if (width) progress.value = withTiming(1, { duration: DRAW_MS, easing: EASE_OUT, reduceMotion: ReduceMotion.System });
  }, [width, progress]);
  const animatedProps = useAnimatedProps(() => ({ strokeDashoffset: length * (1 - progress.value) }));

  const rising = gauge.trend === 'rising';
  const delta = gauge.series[gauge.series.length - 1] - gauge.series[0];
  const toAction = gauge.actionStageFt - gauge.stageFt;
  const last = gauge.series[gauge.series.length - 1];

  return (
    <View
      style={styles.card}
      accessible
      accessibilityLabel={`${gauge.name}: ${gauge.stageFt.toFixed(1)} feet, ${gauge.trend}. ${toAction.toFixed(1)} feet below action stage. ${gauge.source}.`}
    >
      <View style={styles.top}>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>{gauge.name}</Text>
          <View style={styles.valueRow}>
            <Text style={styles.value}>{gauge.stageFt.toFixed(1)}</Text>
            <Text style={styles.unit}> ft</Text>
            <Text style={[styles.trend, rising && styles.trendRising]}>
              {rising ? `  ▲ ${delta.toFixed(1)} ft in ${hours}h` : '  Steady'}
            </Text>
          </View>
        </View>
        <Text style={styles.meta}>{formatTime(gauge.observedAt)}</Text>
      </View>
      <View onLayout={onLayout} style={styles.chart}>
        {width > 0 ? (
          <Svg width={width} height={CHART_H}>
            <Line x1={0} x2={width} y1={y(gauge.actionStageFt)} y2={y(gauge.actionStageFt)} stroke={color.amber} strokeWidth={1} strokeDasharray="3 4" />
            <AnimatedPath
              d={line}
              stroke={rising ? color.primary : color.secondary}
              strokeWidth={2.25}
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
              strokeDasharray={`${length} ${length}`}
              animatedProps={animatedProps}
            />
            <Circle cx={x(hours)} cy={y(last)} r={3.5} fill={rising ? color.primary : color.secondary} />
          </Svg>
        ) : null}
      </View>
      <Text style={styles.foot}>
        Action stage {gauge.actionStageFt} ft · {toAction.toFixed(1)} ft to go · {gauge.source}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.control + 2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.divider,
    backgroundColor: color.white,
    padding: space.md,
    gap: space.xs,
  },
  top: { flexDirection: 'row', alignItems: 'flex-start' },
  label: { ...font.caption, color: color.secondary },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', marginTop: 2 },
  value: { ...font.title, ...tabular, color: color.ink },
  unit: { ...font.body, color: color.secondary },
  trend: { ...font.small, ...tabular, color: color.secondary },
  trendRising: { color: color.primary, fontWeight: '600' },
  meta: { ...font.caption, ...tabular, color: color.secondary },
  chart: { height: CHART_H, marginTop: 2 },
  foot: { ...font.caption, ...tabular, color: color.secondary },
});
