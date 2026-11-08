import { router } from 'expo-router';
import { StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import Animated, { Extrapolation, interpolate, useAnimatedScrollHandler, useAnimatedStyle, useSharedValue } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Avatar, openDevControls } from '@/components/BlueHeader';
import { GaugeCard } from '@/components/GaugeCard';
import { Icon } from '@/components/Icon';
import { Appear } from '@/components/Motion';
import { PressableScale } from '@/components/PressableScale';
import { ListRow, SectionHeader } from '@/components/Rows';
import { useStatusBar } from '@/components/ScreenHeader';
import { Wordmark } from '@/components/WaveMark';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import { FloodMap } from '@/map/FloodMap';
import { buildScene } from '@/map/scene';
import { formatTime, greeting, selectedRouteAffected } from '@/state/selectors';
import { balanced, color, font, gutter, radius, space, tabular, touchTarget } from '@/theme/tokens';

const SHEET_OVERLAP = 28;
const HERO_MIN = 260;
const HERO_MAX = 420;
const HERO_RATIO = 0.42;

export function HomeScreen() {
  const state = useAppState();
  const repo = useRepository();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const heroH = Math.round(Math.min(Math.max(height * HERO_RATIO, HERO_MIN), HERO_MAX));
  const { user, warning, contact, trip, safetyCase, gauge } = state;
  const routeAffected = selectedRouteAffected(state);
  useStatusBar('dark');

  // Parallax: the map drifts at half speed as the sheet scrolls over it.
  const scrollY = useSharedValue(0);
  const onScroll = useAnimatedScrollHandler((e) => {
    scrollY.value = e.contentOffset.y;
  });
  const heroStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: interpolate(scrollY.value, [-100, 0, heroH], [0, 0, -heroH / 2], Extrapolation.CLAMP) }],
  }));

  const tripSubtitle = !trip.closure
    ? 'No reported closures on your route'
    : routeAffected
      ? `Closure reported on ${trip.closure.road}`
      : `Alternate route via ${trip.routes.alternate.via}`;

  return (
    <View style={styles.screen}>
      <Animated.View style={[styles.hero, { height: heroH }, heroStyle]}>
        <FloodMap
          scene={buildScene(state, 'overview')}
          accessibilityLabel="Map of Kerrville and the Guadalupe River with your location near home"
          rounded={false}
          bottomInset={SHEET_OVERLAP + 8}
          style={StyleSheet.absoluteFill}
        />
      </Animated.View>

      <View style={[styles.topBar, { top: insets.top + 6 }]} pointerEvents="box-none">
        <View style={styles.brandChip}>
          <Wordmark tint={color.ink} onLongPress={openDevControls} />
        </View>
        <Avatar initials={user.initials} onPress={() => router.navigate('/profile')} />
      </View>

      <Animated.ScrollView
        onScroll={onScroll}
        scrollEventThrottle={16}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingTop: heroH - SHEET_OVERLAP }}
      >
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <Appear index={0}>
            <Text style={styles.meta}>{user.homeArea}</Text>
            <Text style={styles.title} accessibilityRole="header" {...balanced}>
              {greeting(new Date().toISOString())}, {user.firstName}
            </Text>
          </Appear>

          <Appear index={1}>
            {safetyCase?.minimized ? (
              <StatusCard tone="info" icon="shieldCheck" label="Help request active" detail="See its status" onPress={() => repo.restoreCase()} />
            ) : warning ? (
              <StatusCard
                tone="hazard"
                icon="warning"
                label={warning.event}
                detail={`${warning.area} · until ${formatTime(warning.expiresAt)}`}
                onPress={() => router.push('/warning')}
              />
            ) : (
              <StatusCard tone="calm" icon="check" label="No flood warnings" detail="Checked just now" />
            )}
          </Appear>

          <Appear index={2}>
            <GaugeCard gauge={gauge} />
          </Appear>

          <Appear index={3} style={styles.section}>
            <SectionHeader title="Before you go" actionLabel="All updates" onAction={() => router.navigate('/updates')} />
            <ListRow icon="briefcase" title={trip.name} subtitle={tripSubtitle} onPress={() => router.navigate('/trips')} showDivider />
            <ListRow icon="person" title="Emergency contact" subtitle={contact.name} onPress={() => router.push('/contact')} />
          </Appear>
        </View>
      </Animated.ScrollView>
    </View>
  );
}

type Tone = 'hazard' | 'calm' | 'info';

interface StatusCardProps {
  tone: Tone;
  icon: 'warning' | 'check' | 'shieldCheck';
  label: string;
  detail: string;
  onPress?: () => void;
}

const TONE: Record<Tone, { bg: string; border: string; tint: string }> = {
  hazard: { bg: color.hazardBg, border: color.hazardBorder, tint: color.amberInk },
  calm: { bg: color.surface, border: color.divider, tint: color.primary },
  info: { bg: color.paleBlue, border: color.paleBlueBorder, tint: color.primary },
};

function StatusCard({ tone, icon, label, detail, onPress }: StatusCardProps) {
  const t = TONE[tone];
  return (
    <PressableScale
      onPress={onPress}
      disabled={!onPress}
      pressedScale={0.985}
      accessibilityRole={onPress ? 'button' : 'text'}
      accessibilityLabel={`${label}. ${detail}`}
      style={[styles.status, { backgroundColor: t.bg, borderColor: t.border }]}
    >
      <Icon name={icon} size={22} color={t.tint} strokeWidth={2} />
      <View style={styles.statusText}>
        <Text style={styles.statusTitle}>{label}</Text>
        <Text style={styles.statusDetail}>{detail}</Text>
      </View>
      {onPress ? <Icon name="chevronRight" size={16} color={color.secondary} strokeWidth={2} /> : null}
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.white },
  hero: { position: 'absolute', top: 0, left: 0, right: 0 },
  topBar: {
    position: 'absolute',
    left: space.md,
    right: space.md,
    zIndex: 2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  brandChip: {
    minHeight: touchTarget,
    justifyContent: 'center',
    paddingHorizontal: 14,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(255,255,255,0.94)',
    boxShadow: '0 1px 2px rgba(19,32,59,0.10), 0 4px 12px rgba(19,32,59,0.08)',
  },
  sheet: {
    minHeight: 640,
    backgroundColor: color.white,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: gutter,
    paddingBottom: space.xxl,
    gap: space.md,
    boxShadow: '0 -1px 0 rgba(19,32,59,0.06), 0 -8px 24px rgba(19,32,59,0.06)',
  },
  handle: { alignSelf: 'center', width: 36, height: 5, borderRadius: 3, backgroundColor: color.divider, marginTop: 8 },
  meta: { ...font.small, color: color.secondary },
  title: { ...font.title, fontSize: 28, lineHeight: 33, color: color.ink, marginTop: 2 },
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
  statusDetail: { ...font.small, ...tabular, color: color.secondary },
  section: { marginTop: space.xs },
});
