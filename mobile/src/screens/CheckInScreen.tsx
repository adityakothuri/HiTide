import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { BackHandler, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ScreenHeader } from '@/components/ScreenHeader';
import { Appear } from '@/components/Motion';
import { Button, EmergencyCallLink } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import { FloodMap } from '@/map/FloodMap';
import { buildScene } from '@/map/scene';
import { balanced, color, font, gutter, radius, space } from '@/theme/tokens';

type Pending = 'safe' | 'help' | null;

export function CheckInScreen() {
  const state = useAppState();
  const repo = useRepository();
  const insets = useSafeAreaInsets();
  const [pending, setPending] = useState<Pending>(null);
  const [error, setError] = useState<string | null>(null);
  const label = state.safetyCase?.locationLabel ?? 'Your location';

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => true);
    return () => sub.remove();
  }, []);

  const respond = async (kind: 'safe' | 'help') => {
    if (pending) return;
    setPending(kind);
    setError(null);
    try {
      if (kind === 'safe') await repo.markSafe();
      else await repo.requestHelp();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Try again.');
      setPending(null);
    }
  };

  return (
    <View style={styles.screen}>
      <ScreenHeader showMark />
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: Math.max(insets.bottom, space.md) }]}
        bounces={false}
      >
        <Appear index={0} style={styles.block}>
        <Text style={styles.eyebrow}>Safety check-in</Text>
        <Text style={styles.title} accessibilityRole="header" {...balanced}>
          Are you safe?
        </Text>
        <Text style={styles.subtitle}>You stopped near a reported flood on {label}.</Text>
        </Appear>
        <Appear index={1} style={styles.block}>

        <FloodMap
          scene={buildScene(state, 'location')}
          accessibilityLabel={`Map of your current location on ${label}`}
          style={styles.map}
        />

        <View style={styles.location} accessible accessibilityLabel={`${label}. Location updated just now`}>
          <Icon name="pin" size={22} color={color.primary} />
          <View>
            <Text style={styles.locationTitle}>{label}</Text>
            <Text style={styles.locationBody}>Location updated just now</Text>
          </View>
        </View>

        </Appear>
        {error ? (
          <Text style={styles.error} accessibilityLiveRegion="assertive" accessibilityRole="alert">
            {error}
          </Text>
        ) : null}

        <Appear index={2} style={styles.actions}>
          <Button
            label="I’m safe"
            onPress={() => respond('safe')}
            isLarge
            isBusy={pending === 'safe'}
            isDisabled={pending !== null}
          />
          <Button
            label="I need help"
            variant="outline"
            onPress={() => respond('help')}
            isLarge
            isBusy={pending === 'help'}
            isDisabled={pending !== null}
          />
        </Appear>
        <EmergencyCallLink onPress={() => router.push('/call-911')} />
        <Text style={styles.footnote}>Check in when you’re stopped.</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.white },
  content: { flexGrow: 1, paddingHorizontal: gutter, paddingTop: space.lg, gap: space.sm },
  eyebrow: { ...font.overline, color: color.secondary, textTransform: 'uppercase' },
  title: { ...font.display, color: color.ink, marginTop: -2 },
  subtitle: { ...font.body, color: color.secondary, marginBottom: space.xs },
  map: { height: 170, marginTop: space.xs },
  location: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: color.paleBlue,
    borderRadius: radius.control,
    padding: space.md,
  },
  locationTitle: { ...font.rowTitle, color: color.ink },
  locationBody: { ...font.small, color: color.secondaryStrong },
  error: { ...font.small, color: color.emergency, textAlign: 'center' },
  actions: { gap: space.sm, marginTop: space.xxs },
  block: { gap: space.sm },
  footnote: { ...font.caption, color: color.secondary, textAlign: 'center' },
});
