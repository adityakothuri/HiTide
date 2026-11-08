import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Line } from 'react-native-svg';
import type { FloodLayer } from '@/domain/types';
import { roadStyle } from '@/map/floodStyle';
import { FloodDot, GaugeDot } from '@/map/markers';
import { formatTime } from '@/state/selectors';
import { color, flood, font, space, tabular } from '@/theme/tokens';

const SWATCH_W = 26;
const SWATCH_H = 10;

function LineSwatch({ status }: { status: 'confirmed_flooded' | 'likely_flooded' | 'unknown' }) {
  const st = roadStyle(status)!;
  return (
    <Svg width={SWATCH_W} height={SWATCH_H}>
      <Line
        x1={2}
        x2={SWATCH_W - 2}
        y1={SWATCH_H / 2}
        y2={SWATCH_H / 2}
        stroke={st.color}
        strokeWidth={st.width - 1}
        strokeDasharray={st.dash ? st.dash.join(' ') : undefined}
        strokeLinecap="round"
      />
    </Svg>
  );
}

function Item({ swatch, label }: { swatch: ReactNode; label: string }) {
  return (
    <View style={styles.item}>
      <View style={styles.swatch}>{swatch}</View>
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

interface FloodLegendProps {
  layer: FloodLayer | null;
}

/** Key for the flood layers, in the dashboard's colours; dash patterns and shapes also carry the meaning. */
export function FloodLegend({ layer }: FloodLegendProps) {
  const source = !layer
    ? 'No flood picture yet'
    : layer.sample
      ? 'Sample data'
      : `${layer.replay ? 'Replay of July 4, 2025' : 'Live'}${layer.at ? ` · ${formatTime(layer.at)}` : ''}`;
  return (
    <View style={styles.wrap} accessible accessibilityLabel={`Map key. Thick red: flooded road. Thin amber: likely flooded. Faint grey: not checked. Diamonds: crossings with water. Circles: river gauges. ${source}.`}>
      <View style={styles.row}>
        <Item swatch={<LineSwatch status="confirmed_flooded" />} label="Flooded" />
        <Item swatch={<LineSwatch status="likely_flooded" />} label="Likely" />
        <Item swatch={<LineSwatch status="unknown" />} label="Not checked" />
      </View>
      <View style={styles.row}>
        <Item swatch={<FloodDot fill={flood.flooded} />} label="Crossing with water" />
        <Item swatch={<GaugeDot fill={flood.gaugeMajor} />} label="River gauge" />
      </View>
      <Text style={styles.source}>{source}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.xs },
  row: { flexDirection: 'row', flexWrap: 'wrap', columnGap: space.md, rowGap: space.xxs },
  item: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  swatch: { width: SWATCH_W, alignItems: 'center' },
  label: { ...font.caption, color: color.ink },
  source: { ...font.caption, ...tabular, color: color.secondary },
});
