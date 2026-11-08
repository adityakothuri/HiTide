import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Button } from '@/components/Button';
import { DirectionsCard } from '@/components/DirectionsCard';
import { Icon } from '@/components/Icon';
import { SheetScreen, sheetText } from '@/components/SheetScreen';
import { useAppState } from '@/data/RepositoryProvider';
import { openDialer, useAssistantCall } from '@/services/assistantCall';
import { formatTime } from '@/state/selectors';
import { color, font, radius, space, tabular, touchTarget } from '@/theme/tokens';

const STATUS: Record<'live' | 'mock' | 'unavailable', string> = {
  live: 'The assistant has your location, the water near you, and your way to higher ground.',
  mock: 'Simulated call: in this demo setup no call is placed. Start the backend with HITIDE_ASSISTANT_LIVE=1 to use the real line.',
  unavailable: 'The assistant line isn’t available right now. Use the directions below, and call 911 if you are in danger.',
};

/** The HiTide assistant line: an AI voice agent (ElevenLabs over Photon) that knows this person's situation. */
export function AssistantScreen() {
  const state = useAppState();
  const { call, isPending, error } = useAssistantCall();
  const line = state.assistant;
  const mode = line?.mode ?? 'mock';
  const [dialNote, setDialNote] = useState<string | null>(null);

  return (
    <SheetScreen overline="Voice help" title="HiTide assistant">
      <Text style={sheetText.body}>{STATUS[mode]}</Text>

      {line?.phone ? (
        <Pressable
          onPress={() =>
            void openDialer(line.phone).then((ok) => {
              if (!ok) setDialNote('This device can’t place calls. Dial the number from your phone.');
            })
          }
          accessibilityRole="link"
          accessibilityLabel={`Call the HiTide assistant at ${line.phone}`}
          style={({ pressed }) => [styles.number, pressed && styles.pressed]}
        >
          <Icon name="phone" size={22} color={color.primary} />
          <View style={styles.numberText}>
            <Text style={styles.numberValue}>{line.phone}</Text>
            <Text style={styles.numberHint}>Tap to call, or dial it from any phone</Text>
          </View>
        </Pressable>
      ) : null}

      {dialNote ? <Text style={styles.meta} accessibilityLiveRegion="polite">{dialNote}</Text> : null}
      {line ? <Text style={styles.meta}>Prepared {formatTime(line.requestedAt)}</Text> : null}

      {state.directions ? <DirectionsCard directions={state.directions} /> : null}

      <View style={styles.what}>
        <Text style={sheetText.label}>WHAT THE ASSISTANT DOES</Text>
        <Text style={sheetText.body}>
          Asks if you are safe, tells you where to go, and stays with you. If you need help, it flags responders on the
          HiTide operations dashboard with your location. It is an AI assistant and never calls 911 for you.
        </Text>
      </View>

      {error ? (
        <Text style={styles.error} accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
      <Button label={line ? 'Call again' : 'Call the HiTide assistant'} icon="phone" onPress={() => void call()} isBusy={isPending} />
    </SheetScreen>
  );
}

const styles = StyleSheet.create({
  number: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: touchTarget + 12,
    padding: space.md,
    borderRadius: radius.control,
    backgroundColor: color.paleBlue,
  },
  pressed: { opacity: 0.8 },
  numberText: { flex: 1, gap: 2 },
  numberValue: { ...font.heading, ...tabular, color: color.primary },
  numberHint: { ...font.small, color: color.secondaryStrong },
  meta: { ...font.caption, ...tabular, color: color.secondary },
  what: { gap: space.xxs },
  error: { ...font.small, color: color.emergency },
});
