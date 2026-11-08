import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Avatar, openDevControls } from '@/components/BlueHeader';
import { ConnectionBadge } from '@/components/ConnectionBadge';
import { GaugeCard } from '@/components/GaugeCard';
import { HeroMapScreen, heroChip } from '@/components/HeroMapScreen';
import { Icon } from '@/components/Icon';
import { Appear } from '@/components/Motion';
import { PressableScale } from '@/components/PressableScale';
import { ListRow, SectionHeader } from '@/components/Rows';
import { useStatusBar } from '@/components/ScreenHeader';
import { Wordmark } from '@/components/WaveMark';
import { floodCounts } from '@/data/live/mapFlood';
import { LEVEL_LABEL, levelTone } from '@/domain/riskLevel';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import { buildScene } from '@/map/scene';
import { formatTime, greeting, selectedRouteAffected, warningDetail } from '@/state/selectors';
import { balanced, color, font, radius, risk, space, tabular, touchTarget } from '@/theme/tokens';


export function HomeScreen() {
  const state = useAppState();
  const repo = useRepository();
  const { user, warning, contact, trip, safetyCase, gauge } = state;
  const routeAffected = selectedRouteAffected(state);
  useStatusBar('dark');


  const counts = state.floodLayer ? floodCounts(state.floodLayer) : null;
  const floodSubtitle = counts
    ? counts.flooded > 0
      ? `${counts.flooded} ${counts.flooded === 1 ? 'road' : 'roads'} flooded, ${counts.likely} likely nearby`
      : `${counts.likely} ${counts.likely === 1 ? 'road' : 'roads'} likely flooded nearby`
    : 'Flooded roads, crossings and river gauges';

  const tripSubtitle = !trip.closure
    ? 'No reported closures on your route'
    : routeAffected
      ? `Closure reported on ${trip.closure.road}`
      : `Alternate route via ${trip.routes.alternate.via}`;

  return (
    <HeroMapScreen
      scene={buildScene(state, 'overview')}
      mapLabel="Map of Kerrville and the Guadalupe River with your location near home"
      topBar={
        <>
          <View style={heroChip.chip}>
            <Wordmark tint={color.ink} onLongPress={openDevControls} />
          </View>
          <Avatar initials={user.initials} onPress={() => router.navigate('/profile')} />
        </>
      }
      heroActions={
        <>
          <Pressable
            onPress={() => router.push('/set-location')}
            accessibilityRole="button"
            accessibilityLabel="Set your location on the map"
            style={heroChip.chip}
          >
            <Icon name="pin" size={18} color={color.ink} />
            <Text style={styles.mapButtonText}>Set location</Text>
          </Pressable>
          <Pressable
            onPress={() => router.push('/flood-map')}
            accessibilityRole="button"
            accessibilityLabel="Open the flood map"
            style={heroChip.chip}
          >
            <Icon name="layers" size={18} color={color.ink} />
            <Text style={styles.mapButtonText}>Flood map</Text>
          </Pressable>
        </>
      }
    >
      <Appear index={0}>
        <Text style={styles.meta}>{user.homeArea}</Text>
        <Text style={styles.title} accessibilityRole="header" {...balanced}>
          {greeting(new Date().toISOString())}, {user.firstName}
        </Text>
        <View style={styles.badge}>
          <ConnectionBadge connection={state.connection} />
        </View>
      </Appear>

      <Appear index={1}>
        {safetyCase?.minimized ? (
          <StatusCard tone="info" icon="shieldCheck" label="Help request active" detail="See its status" onPress={() => repo.restoreCase()} />
        ) : warning ? (
          <StatusCard
            tone={levelTone(state.connection.level) === 'critical' ? 'critical' : 'hazard'}
            icon="warning"
            label={warning.event}
            level={state.connection.level && LEVEL_LABEL[state.connection.level] ? `Your risk: ${LEVEL_LABEL[state.connection.level]}` : undefined}
            detail={warningDetail(warning)}
            onPress={() => router.push('/warning')}
          />
        ) : state.connection.kind === 'live' && state.connection.status !== 'live' ? (
          <StatusCard
            tone="info"
            icon="warning"
            label="Can’t check for flooding right now"
            detail="Unknown is not the same as clear. Avoid low-water crossings."
          />
        ) : state.connection.kind === 'live' && state.connection.degraded ? (
          <StatusCard
            tone="info"
            icon="warning"
            label="Some flood data is unavailable"
            detail="No warning found, but that isn’t the same as clear. Avoid low-water crossings."
          />
        ) : state.connection.kind === 'live' && state.connection.level === 'watch' ? (
          <StatusCard
            tone="info"
            icon="warning"
            label="Flood watch near you"
            detail={state.connection.topReason ?? 'Conditions could change quickly.'}
          />
        ) : (
          <StatusCard
            tone="calm"
            icon="check"
            label="No flood warnings"
            detail={state.connection.assessedAt ? `Checked ${formatTime(state.connection.assessedAt)}` : 'Checked just now'}
          />
        )}
      </Appear>

      <Appear index={2}>
        <GaugeCard gauge={gauge} />
      </Appear>

      <Appear index={3} style={styles.section}>
        <SectionHeader title="Before you go" actionLabel="All updates" onAction={() => router.navigate('/updates')} />
        <ListRow icon="layers" title="Flood map" subtitle={floodSubtitle} onPress={() => router.push('/flood-map')} showDivider />
        <ListRow icon="briefcase" title={trip.name} subtitle={tripSubtitle} onPress={() => router.navigate('/trips')} showDivider />
        <ListRow icon="person" title="Emergency contact" subtitle={contact.name} onPress={() => router.push('/contact')} />
      </Appear>
    </HeroMapScreen>
  );
}

type Tone = 'critical' | 'hazard' | 'calm' | 'info';

interface StatusCardProps {
  tone: Tone;
  icon: 'warning' | 'check' | 'shieldCheck';
  label: string;
  detail: string;
  /** Your risk level as the dashboard labels it ("Danger", "Critical", ...). */
  level?: string;
  onPress?: () => void;
}

const TONE: Record<Tone, { bg: string; border: string; tint: string }> = {
  critical: { bg: risk.criticalBg, border: risk.criticalLine, tint: risk.criticalInk },
  hazard: { bg: color.hazardBg, border: color.hazardBorder, tint: color.amberInk },
  calm: { bg: color.surface, border: color.divider, tint: color.primary },
  info: { bg: color.paleBlue, border: color.paleBlueBorder, tint: color.primary },
};

function StatusCard({ tone, icon, label, detail, level, onPress }: StatusCardProps) {
  const t = TONE[tone];
  return (
    <PressableScale
      onPress={onPress}
      disabled={!onPress}
      pressedScale={0.985}
      accessibilityRole={onPress ? 'button' : 'text'}
      accessibilityLabel={`${level ? `${level}. ` : ''}${label}. ${detail}`}
      style={[styles.status, { backgroundColor: t.bg, borderColor: t.border }]}
    >
      <Icon name={icon} size={22} color={t.tint} strokeWidth={2} />
      <View style={styles.statusText}>
        {level ? <Text style={[styles.statusLevel, { color: t.tint }]}>{level}</Text> : null}
        <Text style={styles.statusTitle}>{label}</Text>
        <Text style={styles.statusDetail}>{detail}</Text>
      </View>
      {onPress ? <Icon name="chevronRight" size={16} color={color.secondary} strokeWidth={2} /> : null}
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  mapButtonText: { ...font.small, fontWeight: '600', color: color.ink },
  meta: { ...font.small, color: color.secondary },
  title: { ...font.title, color: color.ink, marginTop: 2 },
  badge: { marginTop: space.xs },
  status: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    borderRadius: radius.control + 2,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: space.md,
    paddingVertical: space.sm + 2,
    minHeight: touchTarget + 12,
  },
  statusText: { flex: 1, gap: 1 },
  statusTitle: { ...font.rowTitle, color: color.ink },
  statusLevel: { ...font.overline },
  statusDetail: { ...font.small, ...tabular, color: color.secondary },
  section: { marginTop: space.xs },
});
