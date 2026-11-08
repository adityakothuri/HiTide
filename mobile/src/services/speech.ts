import * as Speech from 'expo-speech';

const spokenAlertIds = new Set<string>();

const VOICE_OPTIONS: Speech.SpeechOptions = { language: 'en-US', rate: 0.95, pitch: 1.0 };

/**
 * Speaks an alert once per alert id, so re-renders and remounts never repeat it.
 * Failure is silent by design: the visible alert must never depend on audio.
 */
export function speakAlertOnce(alertId: string, text: string): boolean {
  if (spokenAlertIds.has(alertId)) return false;
  spokenAlertIds.add(alertId);
  return speak(text);
}

export function speak(text: string): boolean {
  try {
    Speech.stop();
    Speech.speak(text, VOICE_OPTIONS);
    return true;
  } catch {
    return false;
  }
}

export function stopSpeaking(): void {
  try {
    Speech.stop();
  } catch {
    // Speech engine unavailable; nothing to stop.
  }
}

export const TEST_VOICE_TEXT = 'This is HiTide. Spoken alerts are on.';
