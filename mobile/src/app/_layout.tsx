import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useState } from 'react';
import { Platform, StyleSheet } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { IntroOverlay } from '@/components/IntroOverlay';
import { WaveTransition } from '@/components/WaveTransition';
import { RepositoryProvider } from '@/data/RepositoryProvider';
import { FlowGate } from '@/state/flowGate';
import { color } from '@/theme/tokens';

SplashScreen.preventAutoHideAsync().catch(() => undefined);

/** Card screens rise in under the wave curtain; sheets keep the native modal presentation. */
const SCREEN_OPTIONS = {
  headerShown: false,
  contentStyle: { backgroundColor: color.white },
  animation: 'fade_from_bottom' as const,
};
const FOCUSED_FLOW = { gestureEnabled: false, animation: 'fade' as const, presentation: 'card' as const };
const SHEET = { presentation: 'modal' as const, animation: 'default' as const };
/** Set location: a full-height map, so it covers the screen rather than a card sheet. */
const FULL_MAP = { presentation: 'fullScreenModal' as const, gestureEnabled: false };

export default function RootLayout() {
  // The intro starts as the native splash hides; both share the brand blue, so the hand-off is seamless.
  const [ready, setReady] = useState(false);
  const hideSplash = useCallback(() => {
    SplashScreen.hideAsync().catch(() => undefined);
    setReady(true);
  }, []);

  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <RepositoryProvider onReady={hideSplash}>
          <FlowGate />
          <Stack screenOptions={SCREEN_OPTIONS}>
            <Stack.Screen name="(tabs)" options={{ presentation: 'card' }} />
            <Stack.Screen name="turn-around" options={FOCUSED_FLOW} />
            <Stack.Screen name="check-in" options={FOCUSED_FLOW} />
            <Stack.Screen name="support" options={FOCUSED_FLOW} />
            <Stack.Screen name="resolved" options={FOCUSED_FLOW} />
            <Stack.Screen name="warning" options={SHEET} />
            <Stack.Screen name="route-details" options={SHEET} />
            <Stack.Screen name="contact" options={SHEET} />
            <Stack.Screen name="call-911" options={SHEET} />
            <Stack.Screen name="assistant" options={SHEET} />
            <Stack.Screen name="flood-map" options={SHEET} />
            <Stack.Screen name="set-location" options={FULL_MAP} />
            <Stack.Screen name="location-result" options={SHEET} />
            <Stack.Screen name="dev" options={SHEET} />
            <Stack.Screen name="dev-action" options={{ presentation: 'card', animation: 'none' }} />
          </Stack>
          <WaveTransition />
          <IntroOverlay ready={ready} />
        </RepositoryProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

/** On web (quick browser preview), keep the app at phone width instead of stretching to the window. */
const PHONE_MAX_WIDTH = 430;

const styles = StyleSheet.create({
  root: Platform.select({
    web: { flex: 1, width: '100%', maxWidth: PHONE_MAX_WIDTH, alignSelf: 'center', boxShadow: '0 0 0 1px rgba(19,32,59,0.08)' },
    default: { flex: 1 },
  }),
});
