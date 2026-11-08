import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from 'react-native';
import { Button } from '@/components/Button';
import { IconBadge } from '@/components/Rows';
import { SheetScreen, sheetText } from '@/components/SheetScreen';
import { UPDATE_IDS } from '@/data/fixtures';
import { useAppState, useRepository } from '@/data/RepositoryProvider';
import { validateContact } from '@/data/repository';
import type { EmergencyContact } from '@/domain/types';
import { color, font, radius, space, touchTarget } from '@/theme/tokens';

export function ContactScreen() {
  const { contact } = useAppState();
  const repo = useRepository();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState<EmergencyContact>(contact);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [saved, setSaved] = useState(false);
  const validation = validateContact(draft);

  useEffect(() => {
    repo.markRead(UPDATE_IDS.contact);
  }, [repo]);

  const startEdit = () => {
    setDraft(contact);
    setIsEditing(true);
    setSaved(false);
    setShowErrors(false);
  };

  const save = async () => {
    setShowErrors(true);
    if (!validation.ok) return;
    setIsSaving(true);
    setError(null);
    try {
      await repo.updateContact(draft);
      setIsEditing(false);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t save. Try again.');
    } finally {
      setIsSaving(false);
    }
  };

  const footer = isEditing ? (
    <>
      {error ? (
        <Text style={styles.error} accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
      <Button label="Save contact" onPress={save} isBusy={isSaving} />
      <Button label="Cancel" variant="quiet" onPress={() => setIsEditing(false)} isDisabled={isSaving} />
    </>
  ) : (
    <Button label="Edit contact" variant="outline" onPress={startEdit} />
  );

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <SheetScreen overline="Emergency contact" title={isEditing ? 'Edit contact' : contact.name} footer={footer}>
        {isEditing ? (
          <View style={styles.form}>
            <Field
              label="Name"
              value={draft.name}
              error={showErrors ? validation.errors.name : undefined}
              onChange={(name) => setDraft({ ...draft, name })}
              autoComplete="name"
            />
            <Field
              label="Relationship"
              value={draft.relationship}
              error={showErrors ? validation.errors.relationship : undefined}
              onChange={(relationship) => setDraft({ ...draft, relationship })}
            />
            <Field
              label="Mobile number"
              value={draft.phone}
              error={showErrors ? validation.errors.phone : undefined}
              onChange={(phone) => setDraft({ ...draft, phone })}
              keyboardType="phone-pad"
              autoComplete="tel"
            />
          </View>
        ) : (
          <>
            {saved ? (
              <Text style={styles.saved} accessibilityLiveRegion="polite">
                Contact saved.
              </Text>
            ) : null}
            <View style={styles.card}>
              <IconBadge name="person" size={52} background={color.white} />
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={styles.name}>{contact.name}</Text>
                {contact.relationship ? <Text style={sheetText.muted}>{contact.relationship}</Text> : null}
                <Text style={styles.phone}>{contact.phone}</Text>
              </View>
            </View>
            <Text style={sheetText.muted}>
              If you ask for help, HiTide lets {contact.name.split(' ')[0]} know where you are. In this demo,
              notifications are simulated and nothing is sent.
            </Text>
          </>
        )}
      </SheetScreen>
    </KeyboardAvoidingView>
  );
}

interface FieldProps {
  label: string;
  value: string;
  error?: string;
  onChange: (v: string) => void;
  keyboardType?: 'default' | 'phone-pad';
  autoComplete?: 'name' | 'tel';
}

function Field({ label, value, error, onChange, keyboardType = 'default', autoComplete }: FieldProps) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        accessibilityLabel={label}
        keyboardType={keyboardType}
        autoComplete={autoComplete}
        maxLength={60}
        style={[styles.input, error && styles.inputError]}
        placeholderTextColor={color.secondary}
      />
      {error ? <Text style={styles.fieldError}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: space.md },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    padding: space.md,
    borderRadius: radius.panel,
    backgroundColor: color.paleBlue,
  },
  name: { ...font.heading, color: color.ink },
  phone: { ...font.rowTitle, color: color.ink, marginTop: 2 },
  saved: { ...font.rowTitle, color: color.primary },
  field: { gap: 6 },
  fieldLabel: { ...font.small, fontWeight: '600', color: color.ink },
  input: {
    minHeight: touchTarget + 4,
    borderRadius: radius.control,
    borderWidth: 1.5,
    borderColor: color.divider,
    paddingHorizontal: space.md,
    ...font.body,
    color: color.ink,
  },
  inputError: { borderColor: color.emergency },
  fieldError: { ...font.caption, color: color.emergency },
  error: { ...font.small, color: color.emergency, textAlign: 'center' },
});
