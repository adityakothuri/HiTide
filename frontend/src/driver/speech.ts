// Spoken alerts via the Web Speech API. Browsers block speech until the page has had a user
// gesture, so Settings has a "Test spoken alert" button that also unlocks audio for the demo.

let enabled = true

export function setSpokenAlerts(on: boolean): void {
  enabled = on
  if (!on) stopSpeaking()
}

export function spokenAlertsOn(): boolean {
  return enabled
}

// Held at module level so Chrome doesn't garbage-collect the utterance mid-sentence.
let current: SpeechSynthesisUtterance | null = null

/**
 * Speaks `text`. `onChange(true)` fires when audio actually starts and `onChange(false)` when it ends
 * or the browser blocks it (no user gesture yet), so the UI never claims to speak when it isn't.
 */
export function speak(text: string, onChange?: (speaking: boolean) => void): boolean {
  if (!enabled || typeof window === 'undefined' || !('speechSynthesis' in window)) return false
  const synth = window.speechSynthesis
  if (synth.speaking || synth.pending) synth.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.rate = 0.95
  u.lang = 'en-US'
  u.onstart = () => onChange?.(true)
  u.onend = () => onChange?.(false)
  u.onerror = () => onChange?.(false)
  current = u
  synth.speak(current)
  return true
}

export function stopSpeaking(): void {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel()
}
