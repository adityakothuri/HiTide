import { router } from 'expo-router';
import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { SheetScreen, sheetText } from '@/components/SheetScreen';
import { UPDATE_IDS } from '@/data/fixtures';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import { formatTime } from '@/state/selectors';
import { color, font, radius, space } from '@/theme/tokens';

export function WarningScreen() {
  const { warning } = useAppState();
  const repo = useRepository();

  useEffect(() => {
    if (warning) repo.markRead(UPDATE_IDS.warning);
  }, [warning, repo]);

  if (!warning) {
    return (
      <SheetScreen title="No active warnings">
        <Text style={sheetText.body}>There are no flood warnings for your area right now.</Text>
      </SheetScreen>
    );
  }

  return (
    <SheetScreen
      overline={warning.area}
      title={warning.event}
      footer={
        <Button
          label="Review your trip"
          icon="car"
          onPress={() => {
            router.back();
            router.navigate('/trips');
          }}
        />
      }
    >
      <View style={styles.banner}>
        <Icon name="warning" size={26} color={color.amberInk} strokeWidth={2.2} />
        <Text style={styles.bannerText}>Flood warning in your area</Text>
      </View>

      <View style={styles.facts}>
        <Fact label="Source" value={warning.source} />
        {warning.issuedAt ? <Fact label="Issued" value={formatTime(warning.issuedAt)} /> : null}
        {warning.expiresAt ? <Fact label="Expires" value={formatTime(warning.expiresAt)} /> : null}
        {warning.assessedAt ? <Fact label="Checked for you" value={formatTime(warning.assessedAt)} /> : null}
      </View>

      <Text style={sheetText.body}>{warning.summary}</Text>
      <View style={styles.guidance}>
        <Text style={sheetText.label}>WHAT TO DO</Text>
        <Text style={styles.guidanceText}>{warning.guidance}</Text>
      </View>
      <Text style={sheetText.muted}>
        A warning describes the area, not individual roads. Conditions can change quickly.
      </Text>
    </SheetScreen>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fact}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={styles.factValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: '#FFF6E2',
    borderRadius: radius.control,
    padding: space.md,
  },
  bannerText: { ...font.rowTitle, color: color.ink },
  facts: { borderRadius: radius.control, borderWidth: 1, borderColor: color.divider },
  fact: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: space.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.divider,
  },
  factLabel: { ...font.small, color: color.secondary },
  factValue: { ...font.small, fontWeight: '600', color: color.ink, flexShrink: 1, textAlign: 'right' },
  guidance: { backgroundColor: color.paleBlue, borderRadius: radius.control, padding: space.md, gap: 4 },
  guidanceText: { ...font.rowTitle, color: color.ink },
});
