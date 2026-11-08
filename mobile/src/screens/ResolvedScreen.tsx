import { useEffect } from 'react';
import { BackHandler, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ScreenHeader } from '@/components/ScreenHeader';
import Animated, { ReduceMotion, ZoomIn } from 'react-native-reanimated';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import { formatTime } from '@/state/selectors';
import { balanced, color, font, gutter, radius, space, tabular } from '@/theme/tokens';

export function ResolvedScreen() {
  const state = useAppState();
  const repo = useRepository();
  const insets = useSafeAreaInsets();
  const safeAt = state.safetyCase?.events.find((e) => e.kind === 'marked_safe')?.at;
  const helpWasRequested = state.safetyCase?.events.some((e) => e.kind === 'help_received') ?? false;

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      repo.dismissResolved();
      return true;
    });
    return () => sub.remove();
  }, [repo]);

  return (
    <View style={styles.screen}>
      <ScreenHeader showMark />
      <View style={[styles.content, { paddingBottom: Math.max(insets.bottom, space.lg) }]}>
        <View style={styles.main} accessible accessibilityRole="alert">
          <Animated.View entering={ZoomIn.springify().damping(12).reduceMotion(ReduceMotion.System)} style={styles.check}>
            <Icon name="check" size={22} color={color.white} strokeWidth={2.6} />
          </Animated.View>
          <Text style={styles.title} {...balanced}>You’re marked safe.</Text>
          <Text style={styles.body}>
            {helpWasRequested
              ? 'Your help request is closed.'
              : `We won’t notify ${state.contact.name}.`}{' '}
            Stay clear of floodwater and check updates before you drive again.
          </Text>
          {safeAt ? (
            <View style={styles.stamp}>
              <Icon name="clock" size={18} color={color.secondaryStrong} />
              <Text style={styles.stampText}>Checked in at {formatTime(safeAt)}</Text>
            </View>
          ) : null}
        </View>
        <Button label="Back to Home" onPress={() => repo.dismissResolved()} isLarge />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.white },
  content: { flex: 1, paddingHorizontal: gutter, justifyContent: 'space-between' },
  main: { flex: 1, justifyContent: 'center', gap: space.sm },
  check: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: color.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: space.xs,
  },
  title: { ...font.display, color: color.ink },
  body: { ...font.body, color: color.secondary },
  stamp: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: color.paleBlue,
    borderRadius: radius.pill,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  stampText: { ...font.small, ...tabular, color: color.secondaryStrong },
});
