import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { Avatar } from '@/components/BlueHeader';
import { enterUp } from '@/components/Motion';
import { ScreenHeader } from '@/components/ScreenHeader';
import Animated from 'react-native-reanimated';
import { Button } from '@/components/Button';
import { useAppState } from '@/data/RepositoryProvider';
import type { AppState } from '@/domain/types';
import { FloodMap } from '@/map/FloodMap';
import { buildScene } from '@/map/scene';
import { formatTime } from '@/state/selectors';
import { color, font, gutter, radius, shadow, space, tabular } from '@/theme/tokens';

interface SheetCopy {
  overline: string;
  title: string;
  body: string;
  distanceMi: number;
  durationMin: number;
  via: string;
  action: string;
  isPrimary: boolean;
}

function sheetCopy(state: AppState): SheetCopy {
  const { trip, selectedRouteId } = state;
  const alt = trip.routes.alternate;
  const usual = trip.routes.original;
  if (!trip.closure) {
    return {
      overline: 'Your route',
      title: `Via ${usual.via}`,
      body: 'No reported closures on this route.',
      distanceMi: usual.distanceMi,
      durationMin: usual.durationMin,
      via: usual.via,
      action: 'View route details',
      isPrimary: false,
    };
  }
  if (selectedRouteId === 'alternate') {
    return {
      overline: 'Alternate route',
      title: `Via ${alt.via}`,
      body: `Avoids the closure reported on ${trip.closure.road}.`,
      distanceMi: alt.distanceMi,
      durationMin: alt.durationMin,
      via: alt.via,
      action: 'View route details',
      isPrimary: false,
    };
  }
  return {
    overline: 'Route update',
    title: `${trip.closure.road} is closed`,
    body: `Reported ${formatTime(trip.closure.reportedAt)} · ${trip.closure.source}`,
    distanceMi: alt.distanceMi,
    durationMin: alt.durationMin,
    via: alt.via,
    action: 'Review alternate route',
    isPrimary: true,
  };
}

export function TripsScreen() {
  const state = useAppState();
  const copy = sheetCopy(state);
  const { trip, user } = state;

  return (
    <View style={styles.screen}>
      <ScreenHeader
        title="Your trip"
        subtitle={`${trip.from} → ${trip.to}`}
        onBack={() => router.navigate('/')}
        backLabel="Back to Home"
        right={<Avatar initials={user.initials} onPress={() => router.navigate('/profile')} />}
      />

      <FloodMap
        scene={buildScene(state, 'route')}
        accessibilityLabel="Route map from home to work"
        interactive
        showControls
        rounded={false}
        bottomInset={radius.panel + 4}
        style={styles.map}
      />

      <Animated.View entering={enterUp(1)} style={[styles.sheet, shadow.panel]}>
        <View style={styles.handle} />
        <Text style={styles.overline}>{copy.overline}</Text>
        <Text style={styles.sheetTitle} accessibilityRole="header">
          {copy.title}
        </Text>
        <Text style={styles.sheetBody}>{copy.body}</Text>
        <View style={styles.facts}>
          <Text style={styles.fact}>{copy.distanceMi.toFixed(1)} mi</Text>
          <View style={styles.factRule} />
          <Text style={styles.factMuted}>about {copy.durationMin} min · via {copy.via}</Text>
        </View>
        <Button
          label={copy.action}
          icon={copy.isPrimary ? 'navigate' : 'route'}
          variant={copy.isPrimary ? 'primary' : 'outline'}
          onPress={() => router.push('/route-details')}
        />
        <Text style={styles.footnote}>
          Conditions can change. <Text style={styles.footnoteStrong}>Avoid floodwater.</Text>
        </Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.white },
  title: { ...font.title, fontSize: 24, lineHeight: 29, color: color.white },
  map: { flex: 1, minHeight: 180 },
  sheet: {
    marginTop: -radius.panel,
    backgroundColor: color.white,
    borderTopLeftRadius: radius.panel,
    borderTopRightRadius: radius.panel,
    paddingHorizontal: gutter,
    paddingTop: space.xs,
    paddingBottom: space.md,
    gap: space.xs,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 5,
    borderRadius: 3,
    backgroundColor: color.divider,
    marginBottom: space.xs,
  },
  overline: { ...font.overline, color: color.secondary, textTransform: 'uppercase' },
  sheetTitle: { ...font.title, color: color.ink },
  sheetBody: { ...font.body, color: color.secondary },
  facts: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.divider,
    paddingTop: space.sm,
    paddingBottom: space.xs,
    marginTop: space.xxs,
  },
  fact: { ...font.rowTitle, ...tabular, color: color.ink },
  factRule: { width: 1, height: 18, backgroundColor: color.divider },
  factMuted: { ...font.body, color: color.secondary, flexShrink: 1 },
  footnote: { ...font.caption, color: color.secondary, textAlign: 'center', marginTop: space.xxs },
  footnoteStrong: { color: color.ink, fontWeight: '600' },
});
