import type { AppState, EmergencyContact, Preferences, RouteId, Scenario } from '@/domain/types';

/**
 * The single data boundary between screens and any backend.
 * Today: MockFloodWatchRepository (local fixtures + AsyncStorage).
 * Later: a SpaceTimeDB-backed adapter implements this same interface.
 */
export interface FloodWatchRepository {
  /** Loads persisted preferences and contact. Resolves once state is ready. */
  load(): Promise<void>;
  getSnapshot(): AppState;
  /** Returns an unsubscribe function. */
  subscribe(listener: () => void): () => void;

  selectRoute(routeId: RouteId): Promise<void>;
  markRead(updateId: string): void;
  updateContact(contact: EmergencyContact): Promise<void>;
  setPreferences(patch: Partial<Preferences>): Promise<void>;
  acknowledgeTurnAround(): void;
  markSafe(): Promise<void>;
  requestHelp(): Promise<void>;
  minimizeCase(): void;
  restoreCase(): void;
  dismissResolved(): void;

  /** Development scenario controls. Not part of the consumer navigation. */
  setScenario(scenario: Scenario): void;
  reset(): Promise<void>;
  setSimulateFailures(enabled: boolean): void;
  readonly simulateFailures: boolean;
  dispose(): void;
}

export class RepositoryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RepositoryError';
  }
}

export interface ContactValidation {
  ok: boolean;
  errors: Partial<Record<keyof EmergencyContact, string>>;
}

const PHONE_DIGITS = /\d/g;
const MIN_PHONE_DIGITS = 10;
const MAX_NAME_LENGTH = 60;

export function validateContact(c: EmergencyContact): ContactValidation {
  const errors: ContactValidation['errors'] = {};
  const name = c.name.trim();
  if (!name) errors.name = 'Enter a name.';
  else if (name.length > MAX_NAME_LENGTH) errors.name = 'Use 60 characters or fewer.';
  if (c.relationship.trim().length > MAX_NAME_LENGTH) errors.relationship = 'Use 60 characters or fewer.';
  const digits = (c.phone.match(PHONE_DIGITS) ?? []).length;
  if (digits < MIN_PHONE_DIGITS || digits > 15 || /[^\d\s()+.-]/.test(c.phone)) {
    errors.phone = 'Enter a 10-digit phone number.';
  }
  return { ok: Object.keys(errors).length === 0, errors };
}
