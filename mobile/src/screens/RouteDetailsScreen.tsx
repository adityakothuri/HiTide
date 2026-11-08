import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { SheetScreen, sheetText } from '@/components/SheetScreen';
import { UPDATE_IDS } from '@/data/fixtures';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import type { RouteId, RouteOption } from '@/domain/types';
import { FloodMap } from '@/map/FloodMap';
import { buildScene } from '@/map/scene';
import { formatTime } from '@/state/selectors';
import { color, font, radius, space, touchTarget } from '@/theme/tokens';

export function RouteDetailsScreen() {
  const state = useAppState();
  const repo = useRepository();
  const { trip, selectedRouteId } = state;
  const [choice, setChoice] = useState<RouteId>(trip.closure ? 'alternate' : 'original');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    repo.markRead(UPDATE_IDS.routeChanged);
    repo.markRead(UPDATE_IDS.routeSelected);
    repo.markRead(UPDATE_IDS.turnAround);
  }, [repo]);

  const save = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await repo.selectRoute(choice);
      router.back();
      router.navigate('/trips');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t update your route.');
    } finally {
      setIsSaving(false);
    }
  };

  const options: RouteOption[] = trip.closure ? [trip.routes.alternate, trip.routes.original] : [trip.routes.original];
  const unchanged = choice === selectedRouteId;
  const closure = trip.closure;

  return (
    <SheetScreen
      overline={`${trip.from} → ${trip.to}`}
      title="Route details"
      footer={
        <>
          {error ? (
            <Text style={styles.error} accessibilityRole="alert">
              {error}
            </Text>
          ) : null}
          <Button
            label={unchanged ? 'Done' : choice === 'alternate' ? 'Use alternate route' : 'Use usual route'}
            onPress={unchanged ? () => router.back() : save}
            isBusy={isSaving}
          />
        </>
      }
    >
      <FloodMap scene={buildScene(state, 'route')} accessibilityLabel="Map comparing both routes" style={styles.map} />

      <View style={styles.options} accessibilityRole="radiogroup">
        {options.map((r) => (
          <RouteCard
            key={r.id}
            route={r}
            isChosen={choice === r.id}
            isCurrent={selectedRouteId === r.id}
            note={
              r.affectedRoad && closure
                ? `Closure reported on ${closure.road} · ${formatTime(closure.reportedAt)}`
                : closure
                  ? `Avoids the reported closure on ${closure.road}`
                  : 'No reported closures'
            }
            isAffected={!!(r.affectedRoad && closure)}
            onPress={() => setChoice(r.id)}
          />
        ))}
      </View>

      {closure ? (
        <View style={styles.source}>
          <Text style={sheetText.label}>SOURCE</Text>
          <Text style={sheetText.body}>{closure.source}</Text>
        </View>
      ) : null}
      <Text style={sheetText.muted}>
        An alternate route avoids roads with reported closures. It isn’t guaranteed safe. Conditions can change, so never
        drive into floodwater.
      </Text>
    </SheetScreen>
  );
}

interface RouteCardProps {
  route: RouteOption;
  isChosen: boolean;
  isCurrent: boolean;
  isAffected: boolean;
  note: string;
  onPress: () => void;
}

function RouteCard({ route, isChosen, isCurrent, isAffected, note, onPress }: RouteCardProps) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ checked: isChosen }}
      accessibilityLabel={`${route.label} via ${route.via}, ${route.distanceMi} miles, about ${route.durationMin} minutes. ${note}${isCurrent ? '. Current route' : ''}`}
      style={[styles.card, isChosen && styles.cardChosen]}
    >
      <View style={[styles.radio, isChosen && styles.radioOn]}>{isChosen ? <View style={styles.radioDot} /> : null}</View>
      <View style={{ flex: 1, gap: 2 }}>
        <View style={styles.cardTop}>
          <Text style={styles.cardTitle}>{route.label}</Text>
          {isCurrent ? <Text style={styles.current}>Current</Text> : null}
        </View>
        <Text style={styles.cardMeta}>
          {route.distanceMi.toFixed(1)} mi · about {route.durationMin} min · via {route.via}
        </Text>
        <View style={styles.noteRow}>
          <Icon
            name={isAffected ? 'warning' : 'check'}
            size={16}
            color={isAffected ? color.amberInk : color.primary}
            strokeWidth={2.2}
          />
          <Text style={[styles.note, isAffected && { color: color.amberInk }]}>{note}</Text>
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  map: { height: 200 },
  options: { gap: space.sm },
  card: {
    flexDirection: 'row',
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.control,
    borderWidth: 1.5,
    borderColor: color.divider,
    minHeight: touchTarget,
  },
  cardChosen: { borderColor: color.primary, backgroundColor: color.paleBlue },
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: color.secondary,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  radioOn: { borderColor: color.primary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: color.primary },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  cardTitle: { ...font.rowTitle, color: color.ink },
  current: { ...font.caption, fontWeight: '700', color: color.primary },
  cardMeta: { ...font.small, color: color.secondaryStrong },
  noteRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 },
  note: { ...font.small, color: color.ink, flexShrink: 1 },
  source: { gap: 4 },
  error: { ...font.small, color: color.emergency, textAlign: 'center' },
});
