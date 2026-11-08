import { router } from 'expo-router';
import { useEffect } from 'react';
import { ActivityIndicator, BackHandler, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ScreenHeader } from '@/components/ScreenHeader';
import { enterUp } from '@/components/Motion';
import Animated, { ReduceMotion, ZoomIn } from 'react-native-reanimated';
import { Button, EmergencyCallLink } from '@/components/Button';
import { DirectionsCard } from '@/components/DirectionsCard';
import { Icon } from '@/components/Icon';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import type { CaseEventKind, SafetyCase } from '@/domain/types';
import { FloodMap } from '@/map/FloodMap';
import { buildScene } from '@/map/scene';
import { useAssistantCall } from '@/services/assistantCall';
import { formatTime } from '@/state/selectors';
import { balanced, color, font, gutter, space, tabular, touchTarget } from '@/theme/tokens';

type StepStatus = 'done' | 'active' | 'waiting';

const STEP_ORDER: Record<StepStatus, number> = { done: 0, active: 1, waiting: 2 };

interface Step {
  key: string;
  title: string;
  detail: string;
  status: StepStatus;
}

const eventAt = (c: SafetyCase, kind: CaseEventKind): string | undefined => c.events.find((e) => e.kind === kind)?.at;

const tag = (simulated: boolean | undefined): string => (simulated ? ' · Simulated' : '');

function assistantStep(c: SafetyCase): Step | null {
  const e = c.events.find((x) => x.kind === 'assistant_call');
  if (!e) return null;
  const finished = !/^Calling|^Simulated/.test(e.detail ?? '');
  return {
    key: 'assistant',
    title: finished ? 'Talked with the HiTide assistant' : 'HiTide assistant',
    detail: `${formatTime(e.at)} · ${e.detail ?? 'Calling'}${e.simulated ? ' · Simulated' : ''}`,
    status: finished ? 'done' : 'active',
  };
}

function buildSteps(c: SafetyCase, contactName: string, isLive: boolean): Step[] {
  const event = (kind: CaseEventKind) => c.events.find((e) => e.kind === kind);
  const received = eventAt(c, 'help_received');
  const notified = event('contact_notified');
  const responders = event('responders_flagged');
  return [
    {
      key: 'received',
      title: 'Help request received',
      detail: received ? formatTime(received) : 'Sending…',
      status: received ? 'done' : 'active',
    },
    {
      key: 'contact',
      title: 'Emergency contact notified',
      detail: notified
        ? `${contactName} · ${formatTime(notified.at)}${tag(notified.simulated)}`
        : isLive
          ? `${contactName} has not been contacted yet`
          : `Notifying ${contactName}…`,
      status: notified ? 'done' : isLive ? 'waiting' : 'active',
    },
    responders
      ? {
          key: 'operator',
          title: 'Responders flagged',
          detail: `${formatTime(responders.at)}${tag(responders.simulated)} · No response time confirmed`,
          status: 'done',
        }
      : {
          key: 'operator',
          title: 'Awaiting operator update',
          detail: 'No response time confirmed',
          status: 'waiting',
        },
  ];
}

export function SupportScreen() {
  const state = useAppState();
  const repo = useRepository();
  const insets = useSafeAreaInsets();
  const c = state.safetyCase;
  const assistant = useAssistantCall();

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      repo.minimizeCase();
      return true;
    });
    return () => sub.remove();
  }, [repo]);

  if (!c) return null;
  const isLive = state.connection.kind === 'live';
  // Live: the backend notifies its enrolled contact, which may differ from an edit made on this phone.
  const assistantRow = assistantStep(c);
  const base = buildSteps(c, isLive ? 'Your emergency contact' : state.contact.name, isLive);
  const merged = assistantRow ? [base[0], assistantRow, ...base.slice(1)] : base;
  // Completed steps first (in the order they happened), then what is still in progress or waiting.
  const steps = [...merged].sort((a, b) => STEP_ORDER[a.status] - STEP_ORDER[b.status]);
  const anySimulated = !isLive || c.events.some((e) => e.simulated);

  return (
    <View style={styles.screen}>
      <ScreenHeader
        showMark
        right={
          <Pressable
            onPress={() => repo.minimizeCase()}
            accessibilityRole="button"
            accessibilityLabel="Go to Home. Your help request stays active."
            hitSlop={8}
            style={styles.homeButton}
          >
            <Text style={styles.homeText}>Home</Text>
          </Pressable>
        }
      />
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: Math.max(insets.bottom, space.md) }]}
        bounces={false}
      >
        <Text style={styles.eyebrow}>{isLive ? 'Help request' : 'Help request · Sample data'}</Text>
        <Text style={styles.title} accessibilityRole="header" {...balanced}>
          We received your request.
        </Text>
        <Text style={styles.subtitle}>
          This page updates as each step happens.
          {anySimulated ? ' No real call or dispatch is made in this demo.' : ''}
        </Text>

        <FloodMap
          scene={buildScene(state, 'location')}
          accessibilityLabel={`Map of your location on ${c.locationLabel}`}
          style={styles.map}
        />

        <View style={styles.timeline} accessibilityRole="list">
          {steps.map((s, i) => (
            <Animated.View key={s.key} entering={enterUp(i + 1)}>
              <TimelineStep step={s} isLast={i === steps.length - 1} />
            </Animated.View>
          ))}
        </View>

        {state.directions ? <DirectionsCard directions={state.directions} /> : null}

        <Button
          label="Call the HiTide assistant"
          icon="phone"
          onPress={() => void assistant.call()}
          isBusy={assistant.isPending}
          accessibilityHint="Calls an AI voice assistant that knows where you are and how to get to higher ground"
        />
        {assistant.error ? (
          <Text style={styles.error} accessibilityRole="alert">
            {assistant.error}
          </Text>
        ) : null}
        <Button label="View contact details" variant="outline" onPress={() => router.push('/contact')} />
        <EmergencyCallLink onPress={() => router.push('/call-911')} />
        {anySimulated ? <Text style={styles.footnote}>Simulated workflow</Text> : null}
      </ScrollView>
    </View>
  );
}

function TimelineStep({ step, isLast }: { step: Step; isLast: boolean }) {
  const statusText = step.status === 'done' ? 'Complete' : step.status === 'active' ? 'In progress' : 'Waiting';
  return (
    <View style={styles.step} accessible accessibilityLabel={`${step.title}. ${step.detail}. ${statusText}`}>
      <View style={styles.rail}>
        <StepDot status={step.status} />
        {!isLast ? <View style={[styles.line, step.status === 'done' && styles.lineDone]} /> : null}
      </View>
      <View style={styles.stepText}>
        <Text style={styles.stepTitle}>{step.title}</Text>
        <Text style={styles.stepDetail}>{step.detail}</Text>
      </View>
    </View>
  );
}

function StepDot({ status }: { status: StepStatus }) {
  if (status === 'done') {
    return (
      <Animated.View entering={ZoomIn.springify().damping(14).reduceMotion(ReduceMotion.System)} style={[styles.dot, styles.dotDone]}>
        <Icon name="check" size={16} color={color.white} strokeWidth={3} />
      </Animated.View>
    );
  }
  if (status === 'active') {
    return (
      <View style={[styles.dot, styles.dotOpen]}>
        <ActivityIndicator size="small" color={color.primary} />
      </View>
    );
  }
  return <View style={[styles.dot, styles.dotOpen]} />;
}

const DOT = 26;

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.white },
  homeButton: { minHeight: touchTarget, justifyContent: 'center', paddingLeft: space.sm },
  homeText: { ...font.body, color: color.primary },
  error: { ...font.small, color: color.emergency, textAlign: 'center' },
  content: { flexGrow: 1, paddingHorizontal: gutter, paddingTop: space.sm, gap: space.xs + 2 },
  eyebrow: { ...font.overline, color: color.secondary },
  title: { ...font.title, color: color.ink, marginTop: -2 },
  subtitle: { ...font.small, color: color.secondary, marginBottom: space.xs },
  map: { height: 112 },
  timeline: { paddingTop: space.xxs },
  step: { flexDirection: 'row', gap: space.md },
  rail: { width: DOT, alignItems: 'center' },
  dot: { width: DOT, height: DOT, borderRadius: DOT / 2, alignItems: 'center', justifyContent: 'center' },
  dotDone: { backgroundColor: color.primary },
  dotOpen: { borderWidth: 2.5, borderColor: color.primary, backgroundColor: color.white },
  line: { flex: 1, width: 2, backgroundColor: color.divider, marginVertical: 2, minHeight: 14 },
  lineDone: { backgroundColor: color.primary },
  stepText: { flex: 1, paddingBottom: space.sm, gap: 1 },
  stepTitle: { ...font.rowTitle, color: color.ink },
  stepDetail: { ...font.small, ...tabular, color: color.secondary },
  footnote: { ...font.caption, color: color.secondary, textAlign: 'center' },
});
