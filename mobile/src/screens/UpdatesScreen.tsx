import { router } from 'expo-router';
import { useState } from 'react';
import type { LayoutChangeEvent } from 'react-native';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Avatar } from '@/components/BlueHeader';
import { enterUp } from '@/components/Motion';
import { ScreenHeader } from '@/components/ScreenHeader';
import Animated, { LinearTransition, ReduceMotion, useAnimatedStyle, withSpring } from 'react-native-reanimated';
import { Icon, type IconName } from '@/components/Icon';
import { ListRow } from '@/components/Rows';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import type { UpdateItem } from '@/domain/types';
import { formatTime, isRead, type UpdateFilter, visibleUpdates } from '@/state/selectors';
import { color, font, gutter, space, tabular, touchTarget } from '@/theme/tokens';

const FILTERS: { id: UpdateFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'trips', label: 'Trips' },
  { id: 'checkins', label: 'Check-ins' },
];

const ICONS: Record<UpdateItem['icon'], IconName> = {
  warning: 'warning',
  car: 'car',
  person: 'person',
  shield: 'shieldCheck',
  route: 'route',
};

const SEGMENT_PAD = 2;
const TRACK_RADIUS = 10;

export function UpdatesScreen() {
  const state = useAppState();
  const repo = useRepository();
  const [filter, setFilter] = useState<UpdateFilter>('all');
  const [trackW, setTrackW] = useState(0);
  const segW = trackW ? (trackW - SEGMENT_PAD * 2) / FILTERS.length : 0;
  const index = FILTERS.findIndex((f) => f.id === filter);
  const thumbStyle = useAnimatedStyle(() => ({
    width: segW,
    transform: [{ translateX: withSpring(index * segW, { damping: 22, stiffness: 260, reduceMotion: ReduceMotion.System }) }],
  }));
  const items = visibleUpdates(state, filter);

  const open = (item: UpdateItem) => {
    repo.markRead(item.id);
    if (item.target === 'warning' && state.warning) router.push('/warning');
    else if (item.target === 'route') router.push('/route-details');
    else if (item.target === 'contact') router.push('/contact');
    else if (item.target === 'case' && state.safetyCase?.minimized) repo.restoreCase();
  };

  return (
    <View style={styles.screen}>
      <ScreenHeader title="Updates" right={<Avatar initials={state.user.initials} onPress={() => router.navigate('/profile')} />} />

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.track} accessibilityRole="tablist" onLayout={(e: LayoutChangeEvent) => setTrackW(e.nativeEvent.layout.width)}>
          {segW ? <Animated.View style={[styles.thumb, thumbStyle]} /> : null}
          {FILTERS.map((f) => {
            const selected = f.id === filter;
            return (
              <Pressable
                key={f.id}
                onPress={() => setFilter(f.id)}
                accessibilityRole="tab"
                accessibilityState={{ selected }}
                style={styles.segment}
              >
                <Text style={[styles.segmentText, selected && styles.segmentTextOn]}>{f.label}</Text>
              </Pressable>
            );
          })}
        </View>

        <Text style={styles.day} accessibilityRole="header">
          Today
        </Text>
        {items.length === 0 ? (
          <Text style={styles.empty}>Nothing here yet.</Text>
        ) : (
          items.map((item, i) => (
            <Animated.View key={`${filter}-${item.id}`} entering={enterUp(i)} layout={LinearTransition.duration(220)}>
              <UpdateRow item={item} isUnread={!isRead(state, item.id)} showDivider={i < items.length - 1} onPress={() => open(item)} />
            </Animated.View>
          ))
        )}

        <View style={styles.settings}>
          <ListRow
            icon="shieldCheck"
            title="Location and alert settings"
            subtitle="Choose what HiTide can use"
            onPress={() => router.navigate({ pathname: '/profile', params: { section: 'privacy' } })}
          />
        </View>
      </ScrollView>
    </View>
  );
}

interface RowProps {
  item: UpdateItem;
  isUnread: boolean;
  showDivider: boolean;
  onPress: () => void;
}

function UpdateRow({ item, isUnread, showDivider, onPress }: RowProps) {
  const time = formatTime(item.at);
  const isHazard = item.icon === 'warning';
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${isUnread ? 'Unread. ' : ''}${item.title}. ${item.body}. ${time}`}
      accessibilityHint={item.actionLabel}
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
    >
      <View style={styles.unreadCol}>{isUnread ? <View style={styles.unread} /> : null}</View>
      <View style={styles.iconCol}>
        <Icon name={ICONS[item.icon]} size={22} color={isHazard ? color.amberInk : color.secondaryStrong} />
      </View>
      <View style={[styles.rowBody, showDivider && styles.divider]}>
        <View style={styles.rowTop}>
          <Text style={[styles.rowTitle, isUnread && styles.rowTitleUnread]}>{item.title}</Text>
          <Text style={styles.time}>{time}</Text>
        </View>
        <Text style={styles.rowText}>{item.body}</Text>
        {item.actionLabel ? <Text style={styles.action}>{item.actionLabel}</Text> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.white },
  content: { paddingTop: space.xs, paddingBottom: space.xl },
  track: {
    flexDirection: 'row',
    marginHorizontal: gutter,
    padding: SEGMENT_PAD,
    borderRadius: TRACK_RADIUS,
    backgroundColor: color.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: color.divider,
  },
  segment: {
    flex: 1,
    minHeight: 36,
    borderRadius: TRACK_RADIUS - SEGMENT_PAD,
    alignItems: 'center',
    justifyContent: 'center',
  },
  thumb: {
    position: 'absolute',
    top: SEGMENT_PAD,
    bottom: SEGMENT_PAD,
    left: SEGMENT_PAD,
    borderRadius: TRACK_RADIUS - SEGMENT_PAD,
    backgroundColor: color.white,
    boxShadow: '0 1px 2px rgba(19,32,59,0.10), 0 1px 1px rgba(19,32,59,0.04)',
  },
  segmentText: { ...font.small, fontWeight: '500', color: color.secondaryStrong },
  segmentTextOn: { color: color.ink, fontWeight: '600' },
  day: { ...font.overline, color: color.secondary, marginTop: space.lg, marginBottom: space.xxs, paddingHorizontal: gutter },
  empty: { ...font.body, color: color.secondary, paddingHorizontal: gutter, paddingVertical: space.lg },
  row: { flexDirection: 'row', minHeight: touchTarget + 20, paddingRight: gutter },
  rowPressed: { backgroundColor: color.surface },
  unreadCol: { width: gutter - 4, alignItems: 'center', paddingTop: 22 },
  unread: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.primary },
  iconCol: { width: 36, paddingTop: 14 },
  rowBody: { flex: 1, paddingVertical: space.sm, gap: 2 },
  divider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: color.divider },
  rowTop: { flexDirection: 'row', alignItems: 'baseline', gap: space.xs },
  rowTitle: { ...font.rowTitle, fontWeight: '500', color: color.ink, flex: 1 },
  rowTitleUnread: { fontWeight: '600' },
  time: { ...font.caption, ...tabular, color: color.secondary },
  rowText: { ...font.small, color: color.secondary },
  action: { ...font.small, fontWeight: '600', color: color.primary, marginTop: 4 },
  settings: { marginTop: space.lg, paddingHorizontal: gutter },
});
