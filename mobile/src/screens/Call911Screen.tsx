import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { SheetScreen, sheetText } from '@/components/SheetScreen';
import { color, font, radius, space } from '@/theme/tokens';

/**
 * Prototype confirmation. It deliberately never opens the dialer or contacts emergency services.
 * A production build would hand off to the phone app only after explicit confirmation.
 */
export function Call911Screen() {
  return (
    <SheetScreen
      overline="Emergency call"
      title="Call 911?"
      footer={<Button label="Got it" onPress={() => router.back()} />}
    >
      <View style={styles.notice} accessibilityRole="alert">
        <Icon name="info" size={24} color={color.emergency} />
        <Text style={styles.noticeText}>This is a prototype. No call will be placed.</Text>
      </View>
      <Text style={sheetText.body}>
        In a real emergency, call 911 from your phone. If you are in water, get out of the vehicle only if it is safe and
        move to higher ground.
      </Text>
      <Text style={sheetText.muted}>
        HiTide is not an emergency service and does not contact 911, responders, or your contacts in this demo.
      </Text>
    </SheetScreen>
  );
}

const styles = StyleSheet.create({
  notice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    borderRadius: radius.control,
    borderWidth: 1.5,
    borderColor: color.emergency,
    padding: space.md,
  },
  noticeText: { ...font.rowTitle, color: color.emergency, flex: 1 },
});
