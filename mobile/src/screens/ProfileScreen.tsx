import * as Location from 'expo-location';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Linking, Pressable, ScrollView, type ScrollViewInstance, StyleSheet, Switch, Text, View } from 'react-native';
import { Appear } from '@/components/Motion';
import { ScreenHeader } from '@/components/ScreenHeader';
import { Button } from '@/components/Button';
import { ListRow } from '@/components/Rows';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import { speak, TEST_VOICE_TEXT } from '@/services/speech';
import { color, font, radius, space, touchTarget } from '@/theme/tokens';

type LocationNotice = 'denied' | 'error' | null;

export function ProfileScreen() {
  const state = useAppState();
  const repo = useRepository();
  const { section } = useLocalSearchParams<{ section?: string }>();
  const scrollRef = useRef<ScrollViewInstance>(null);
  const [privacyY, setPrivacyY] = useState(0);
  const [locationNotice, setLocationNotice] = useState<LocationNotice>(null);
  const [isRequesting, setIsRequesting] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const highlight = section === 'privacy';
  const { user, contact, preferences } = state;

  useEffect(() => {
    if (highlight && privacyY > 0) scrollRef.current?.scrollTo({ y: privacyY - space.md, animated: true });
  }, [highlight, privacyY]);

  const toggleLocation = async (next: boolean) => {
    setLocationNotice(null);
    if (!next) {
      await repo.setPreferences({ locationSharing: false });
      return;
    }
    setIsRequesting(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status === 'granted') await repo.setPreferences({ locationSharing: true });
      else setLocationNotice('denied');
    } catch {
      setLocationNotice('error');
    } finally {
      setIsRequesting(false);
    }
  };

  const testVoice = () => {
    const ok = speak(TEST_VOICE_TEXT);
    setVoiceNote(ok ? null : 'Spoken alerts aren’t available on this device. Alerts will still appear on screen.');
  };

  return (
    <View style={styles.screen}>
      <ScreenHeader title="Profile" />

      <ScrollView ref={scrollRef} contentContainerStyle={styles.content}>
        <Appear index={0} style={[styles.group, styles.identity]}>
          <View style={styles.bigAvatar}>
            <Text style={styles.bigAvatarText}>{user.initials}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{user.fullName}</Text>
            <Text style={styles.area}>{user.homeArea}</Text>
          </View>
        </Appear>
        <Text style={styles.sectionTitle} accessibilityRole="header">
          Emergency contact
        </Text>
        <View style={styles.group}>
        <ListRow
          icon="person"
          title={contact.name}
          subtitle={[contact.relationship, contact.phone].filter(Boolean).join(' · ')}
          onPress={() => router.push('/contact')}
          accessibilityHint="View or edit your emergency contact"
        />
        </View>

        <Text style={styles.sectionTitle} accessibilityRole="header">
          Location and alerts
        </Text>
        <View
          onLayout={(e) => setPrivacyY(e.nativeEvent.layout.y)}
          style={[styles.panel, highlight && styles.panelHighlight]}
        >

          <SettingRow
            title="Share location during alerts"
            body="Used only to check on you near a reported flood. You can turn this off anytime."
            value={preferences.locationSharing}
            isDisabled={isRequesting}
            onChange={toggleLocation}
          />
          {locationNotice ? (
            <View style={styles.notice} accessibilityLiveRegion="polite">
              <Text style={styles.noticeText}>
                {locationNotice === 'denied'
                  ? 'Location access is off. HiTide will use your saved area, Kerrville, Texas, instead.'
                  : 'We couldn’t check location access. Your saved area will be used instead.'}
              </Text>
              {locationNotice === 'denied' ? (
                <Pressable onPress={() => Linking.openSettings()} accessibilityRole="link" hitSlop={8}>
                  <Text style={styles.noticeLink}>Open Settings</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}
          <View style={styles.rule} />
          <SettingRow
            title="Spoken alerts"
            body="Read urgent alerts aloud so you can keep your eyes on the road."
            value={preferences.spokenAlerts}
            onChange={(v) => repo.setPreferences({ spokenAlerts: v })}
          />
          <Button label="Test voice" icon="speaker" variant="quiet" onPress={testVoice} />
          {voiceNote ? <Text style={styles.noticeText}>{voiceNote}</Text> : null}
        </View>

        <View style={styles.about}>
          <Text style={styles.aboutTitle}>About this demo</Text>
          <Text style={styles.aboutText}>
            HiTide is shown with sample data. Warnings, closures, and help requests are simulated. It never places
            calls or sends messages.
          </Text>
          {__DEV__ ? (
            <Pressable onPress={() => router.push('/dev')} accessibilityRole="button" hitSlop={8}>
              <Text style={styles.devLink}>Developer: scenario controls</Text>
            </Pressable>
          ) : null}
        </View>
      </ScrollView>
    </View>
  );
}

interface SettingRowProps {
  title: string;
  body: string;
  value: boolean;
  isDisabled?: boolean;
  onChange: (v: boolean) => void;
}

function SettingRow({ title, body, value, isDisabled, onChange }: SettingRowProps) {
  return (
    <View style={styles.setting}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.settingTitle}>{title}</Text>
        <Text style={styles.settingBody}>{body}</Text>
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        disabled={isDisabled}
        accessibilityLabel={title}
        trackColor={{ true: color.primary, false: color.divider }}
        thumbColor={color.white}
        ios_backgroundColor={color.divider}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.surface },
  identity: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.md },
  name: { ...font.heading, color: color.ink },
  area: { ...font.small, color: color.secondary },
  bigAvatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: color.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bigAvatarText: { ...font.heading, fontSize: 20, color: color.white },
  content: { padding: space.md, gap: space.xs, paddingBottom: space.xxl },
  sectionTitle: { ...font.overline, color: color.secondary, textTransform: 'uppercase', marginTop: space.md, marginLeft: space.md },
  group: { backgroundColor: color.white, borderRadius: radius.control, paddingHorizontal: space.md },
  panel: {
    gap: space.sm,
    borderRadius: radius.control,
    backgroundColor: color.white,
    padding: space.md,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  panelHighlight: { borderColor: color.primary },
  setting: { flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: touchTarget },
  settingTitle: { ...font.rowTitle, color: color.ink },
  settingBody: { ...font.small, color: color.secondary },
  rule: { height: StyleSheet.hairlineWidth, backgroundColor: color.divider },
  notice: { backgroundColor: color.surface, borderRadius: radius.control, padding: space.sm, gap: 6 },
  noticeText: { ...font.small, color: color.ink },
  noticeLink: { ...font.rowTitle, color: color.primary },
  about: { gap: 6, paddingTop: space.lg, paddingHorizontal: space.md },
  aboutTitle: { ...font.rowTitle, color: color.ink },
  aboutText: { ...font.small, color: color.secondary },
  devLink: { ...font.small, color: color.primary, paddingVertical: space.xs },
});
