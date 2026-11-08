import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Avatar } from '@/components/BlueHeader';
import { Button } from '@/components/Button';
import { HeroMapScreen, heroChip } from '@/components/HeroMapScreen';
import { Icon } from '@/components/Icon';
import { Appear } from '@/components/Motion';
import { useStatusBar } from '@/components/ScreenHeader';
import { RouteChoiceList } from '@/components/RouteChoiceList';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import type { AppState } from '@/domain/types';
import { buildScene } from '@/map/scene';
import { formatTime } from '@/state/selectors';
import { color, font, space, tabular } from '@/theme/tokens';

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

function ChooseRoute({ state }: { state: AppState }) {
  const repo = useRepository();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const choose = async (id: string) => {
    setError(null);
    setPendingId(id);
    try {
      await repo.chooseRoute(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t check that route. Try again.');
    } finally {
      setPendingId(null);
    }
  };
  const chosen = state.routeChoices.find((c) => c.id === state.selectedChoiceId);
  return (
    <>
      <Text style={styles.overline}>{chosen ? 'Your route' : 'Choose a route'}</Text>
      <RouteChoiceList choices={state.routeChoices} selectedId={state.selectedChoiceId} pendingId={pendingId} onChoose={(id) => void choose(id)} />
      {error ? (
        <Text style={styles.error} accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
    </>
  );
}

export function TripsScreen() {
  const state = useAppState();
  const copy = sheetCopy(state);
  const { trip, user } = state;
  const hasChoices = state.routeChoices.length > 0;
  useStatusBar('dark');

  return (
    <HeroMapScreen
      scene={buildScene(state, 'route')}
      mapLabel="Route map from home to work"
      topBar={
        <>
          <Pressable
            onPress={() => router.navigate('/')}
            accessibilityRole="button"
            accessibilityLabel="Back to Home"
            style={heroChip.chip}
          >
            <Icon name="chevronLeft" size={20} color={color.primary} strokeWidth={2.2} />
            <Text style={styles.backText}>Home</Text>
          </Pressable>
          <Avatar initials={user.initials} onPress={() => router.navigate('/profile')} />
        </>
      }
      heroActions={
        <Pressable
          onPress={() => router.push('/flood-map')}
          accessibilityRole="button"
          accessibilityLabel="Open the flood map"
          style={heroChip.chip}
        >
          <Icon name="layers" size={18} color={color.ink} />
          <Text style={styles.chipText}>Flood map</Text>
        </Pressable>
      }
    >
      <Appear index={0}>
        <Text style={styles.title} accessibilityRole="header">
          Your trip
        </Text>
        <Text style={styles.subtitle}>
          {trip.from} → {trip.to}
        </Text>
      </Appear>

      <Appear index={1} style={styles.block}>
        {hasChoices ? (
          <ChooseRoute state={state} />
        ) : (
          <>
            <Text style={styles.overline}>{copy.overline}</Text>
            <Text style={styles.sheetTitle} accessibilityRole="header">
              {copy.title}
            </Text>
            <Text style={styles.sheetBody}>{copy.body}</Text>
            <View style={styles.facts}>
              <Text style={styles.fact}>{copy.distanceMi.toFixed(1)} mi</Text>
              <View style={styles.factRule} />
              <Text style={styles.factMuted}>
                about {copy.durationMin} min · via {copy.via}
              </Text>
            </View>
            <Button
              label={copy.action}
              icon={copy.isPrimary ? 'navigate' : 'route'}
              variant={copy.isPrimary ? 'primary' : 'outline'}
              onPress={() => router.push('/route-details')}
            />
          </>
        )}
        <Text style={styles.footnote}>
          Conditions can change. <Text style={styles.footnoteStrong}>Avoid floodwater.</Text>
        </Text>
      </Appear>
    </HeroMapScreen>
  );
}

const styles = StyleSheet.create({
  title: { ...font.title, color: color.ink, marginTop: 2 },
  subtitle: { ...font.body, color: color.secondary },
  block: { gap: space.xs },
  backText: { ...font.rowTitle, color: color.primary },
  chipText: { ...font.small, fontWeight: '600', color: color.ink },
  overline: { ...font.overline, color: color.secondary },
  sheetTitle: { ...font.heading, color: color.ink },
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
  error: { ...font.small, color: color.emergency, textAlign: 'center' },
  footnote: { ...font.caption, color: color.secondary, textAlign: 'center', marginTop: space.xs },
  footnoteStrong: { color: color.ink, fontWeight: '600' },
});
