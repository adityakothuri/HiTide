import { useEffect } from 'react';
import { BackHandler, Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';
import { openDevControls } from '@/components/BlueHeader';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { Pill } from '@/components/Rows';
import { enterUp, useNudge } from '@/components/Motion';
import { useStatusBar } from '@/components/ScreenHeader';
import Animated from 'react-native-reanimated';
import { Wordmark } from '@/components/WaveMark';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import { FloodMap } from '@/map/FloodMap';
import { buildScene } from '@/map/scene';
import { speakAlertOnce, stopSpeaking } from '@/services/speech';
import { setFlowExit } from '@/state/flowGate';
import { color, font, gutter, radius, space, touchTarget } from '@/theme/tokens';

/** Below this height (e.g. iPhone SE, 667pt) the hero tightens so the action and voice status stay on screen. */
const COMPACT_HEIGHT = 720;

function UTurnArrow({ scale = 1 }: { scale?: number }) {
  return (
    <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants" aria-hidden>
      <Svg width={96 * scale} height={88 * scale} viewBox="0 0 96 88">
      <Path
        d="M70 84V38a24 24 0 0 0-48 0v12"
        stroke={color.white}
        strokeWidth={13}
        strokeLinecap="butt"
        fill="none"
      />
      <Path d="M4 44h36L22 72z" fill={color.white} />
    </Svg>
    </View>
  );
}

/** Urgent, glanceable: one instruction, one action, no typing. */
export function TurnAroundScreen() {
  const state = useAppState();
  const repo = useRepository();
  const insets = useSafeAreaInsets();
  const { alert, preferences, trip } = state;
  const voiceOn = preferences.spokenAlerts;
  const nudge = useNudge(5, 1600);
  const isCompact = useWindowDimensions().height < COMPACT_HEIGHT;
  useStatusBar('light');

  useEffect(() => {
    if (alert && voiceOn) speakAlertOnce(alert.id, alert.spokenText);
  }, [alert, voiceOn]);

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => true);
    return () => sub.remove();
  }, []);

  const toggleVoice = () => {
    if (voiceOn) stopSpeaking();
    void repo.setPreferences({ spokenAlerts: !voiceOn });
  };

  const showAlternate = () => {
    stopSpeaking();
    setFlowExit('/trips');
    repo.acknowledgeTurnAround();
  };

  const road = alert?.road ?? trip.closure?.road ?? 'the road ahead';

  return (
    <View style={styles.screen}>
      <View style={[styles.top, isCompact && styles.topCompact, { paddingTop: insets.top + 8 }]}>
        <View style={styles.bar}>
          <Wordmark onLongPress={openDevControls} />
          <Pressable
            onPress={toggleVoice}
            accessibilityRole="switch"
            accessibilityLabel="Voice guidance"
            accessibilityState={{ checked: voiceOn }}
            hitSlop={8}
            style={styles.voiceButton}
          >
            <Icon name={voiceOn ? 'speaker' : 'speakerOff'} size={28} color={color.white} />
          </Pressable>
        </View>
        <View style={[styles.hero, isCompact && styles.heroCompact]} accessible accessibilityRole="alert" accessibilityLabel="Flooded road ahead. Turn around.">
          <Animated.View entering={enterUp(0)}>
            <Pill label="Voice alert" tone="onBlue" />
          </Animated.View>
          <Animated.View entering={enterUp(1)}>
            <Animated.View style={nudge}>
              <UTurnArrow scale={isCompact ? 0.7 : 1} />
            </Animated.View>
          </Animated.View>
          <Animated.Text entering={enterUp(2)} style={[styles.instruction, isCompact && styles.instructionCompact]} maxFontSizeMultiplier={1.3}>
            Flooded road ahead.{'\n'}Turn around.
          </Animated.Text>
        </View>
      </View>

      <Animated.View entering={enterUp(3)} style={[styles.bottom, { paddingBottom: Math.max(insets.bottom, space.md) }]}>
        <FloodMap
          scene={buildScene(state, 'alert')}
          accessibilityLabel={`Map showing your position and a closure reported on ${road}`}
          style={styles.map}
        />
        <Text style={styles.caption}>Closure reported on {road}</Text>
        <Button label="Show alternate route" onPress={showAlternate} isLarge />
        <View style={styles.voiceRow}>
          <Icon name={voiceOn ? 'speaker' : 'speakerOff'} size={20} color={color.secondary} />
          <Text style={styles.voiceText}>Voice guidance is {voiceOn ? 'on' : 'off'}</Text>
        </View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.primary },
  top: { paddingHorizontal: gutter, paddingBottom: space.xxl },
  bar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: touchTarget },
  voiceButton: { width: touchTarget, height: touchTarget, alignItems: 'flex-end', justifyContent: 'center' },
  topCompact: { paddingBottom: space.lg },
  hero: { alignItems: 'center', gap: space.md, marginTop: space.md },
  heroCompact: { gap: space.xs, marginTop: 0 },
  instruction: { ...font.alert, color: color.white, textAlign: 'center' },
  instructionCompact: { ...font.display },
  bottom: {
    flex: 1,
    backgroundColor: color.white,
    borderTopLeftRadius: radius.panel + 6,
    borderTopRightRadius: radius.panel + 6,
    paddingHorizontal: space.md,
    paddingTop: space.md,
    gap: space.sm,
  },
  map: { flex: 1, minHeight: 120 },
  caption: { ...font.rowTitle, color: color.ink, textAlign: 'center', marginTop: space.xxs },
  voiceRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6 },
  voiceText: { ...font.small, color: color.secondary },
});
