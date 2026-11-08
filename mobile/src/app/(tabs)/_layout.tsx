import { Tabs } from 'expo-router';
import { type ColorValue, Platform, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon, type IconName } from '@/components/Icon';
import { useAppState } from '@/data/RepositoryProvider';
import { unreadCount } from '@/state/selectors';
import { color } from '@/theme/tokens';

function TabIcon({ name, tint, hasDot }: { name: IconName; tint: ColorValue; hasDot?: boolean }) {
  return (
    <View>
      <Icon name={name} size={26} color={String(tint)} />
      {hasDot ? <View style={styles.dot} /> : null}
    </View>
  );
}

const TAB_BAR_HEIGHT = 58;

export default function TabsLayout() {
  const state = useAppState();
  const insets = useSafeAreaInsets();
  const unread = unreadCount(state);
  const bottom = Math.max(insets.bottom, Platform.OS === 'android' ? 8 : 10);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: color.primary,
        tabBarInactiveTintColor: color.secondary,
        tabBarLabelStyle: styles.label,
        tabBarStyle: [styles.bar, { height: TAB_BAR_HEIGHT + bottom, paddingBottom: bottom }],
        tabBarItemStyle: styles.item,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: 'Home', tabBarIcon: ({ color: c }) => <TabIcon name="home" tint={c} /> }}
      />
      <Tabs.Screen
        name="trips"
        options={{ title: 'Trips', tabBarIcon: ({ color: c }) => <TabIcon name="car" tint={c} /> }}
      />
      <Tabs.Screen
        name="updates"
        options={{
          title: 'Updates',
          tabBarAccessibilityLabel: unread > 0 ? `Updates, ${unread} unread` : 'Updates',
          tabBarIcon: ({ color: c }) => <TabIcon name="bell" tint={c} hasDot={unread > 0} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: 'Profile', tabBarIcon: ({ color: c }) => <TabIcon name="person" tint={c} /> }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  bar: {
    backgroundColor: color.white,
    borderTopColor: color.divider,
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: 6,
  },
  item: { paddingTop: 2 },
  label: { fontSize: 12, fontWeight: '600', marginTop: 2 },
  dot: {
    position: 'absolute',
    top: -1,
    right: -3,
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: color.primary,
    borderWidth: 1.5,
    borderColor: color.white,
  },
});
