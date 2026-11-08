import type { AppState, AssistantLine, EmergencyContact, LngLat, Preferences, RouteId, Scenario } from '@/domain/types';

/**
 * The single data boundary between screens and any backend.
 * Today: MockHiTideRepository (local fixtures + AsyncStorage).
 * Later: a SpaceTimeDB-backed adapter implements this same interface.
 */
export interface HiTideRepository {
  /** Loads persisted preferences and contact. Resolves once state is ready. Safe to call more than once. */
  load(): Promise<void>;
  /** Starts background work (polling, sockets). Idempotent; call after load(). */
  start(): void;
  /** Stops background work. start() may be called again later (remounts, Fast Refresh). */
  stop(): void;
  getSnapshot(): AppState;
  /** Returns an unsubscribe function. */
  subscribe(listener: () => void): () => void;

  selectRoute(routeId: RouteId): Promise<void>;
  /** Choose one of `routeChoices`; the backend checks every road on it (pre-trip). */
  chooseRoute(choiceId: string): Promise<void>;
  markRead(updateId: string): void;
  updateContact(contact: EmergencyContact): Promise<void>;
  setPreferences(patch: Partial<Preferences>): Promise<void>;
  acknowledgeTurnAround(): void;
  markSafe(): Promise<void>;
  requestHelp(): Promise<void>;
  /**
   * Prepare the HiTide assistant line: the backend gives the agent this person's situation and directions.
   * Returns the line (live: the number to dial). Never dials by itself; the screen opens the dialer.
   */
  callAssistant(): Promise<AssistantLine>;
  /**
   * Set the person's location to a point picked on the map (stopped, speed 0). The backend assesses it, and may open
   * a case and call them. The outcome is in `lastPin`, `connection.level` and `directions`.
   */
  setLocation(at: LngLat): Promise<void>;
  minimizeCase(): void;
  restoreCase(): void;
  dismissResolved(): void;

  /** Development scenario controls. Not part of the consumer navigation. */
  setScenario(scenario: Scenario): void;
  /** Clears saved data and returns to the default picture (live mode: resumes following the backend). */
  reset(): Promise<void>;
  /** True when a demo drive can send location pings to a backend (live mode only). */
  readonly supportsDemoDrive: boolean;
  /** Development: drive the trip's usual route and stop at the flooded crossing. Status is in `connection.drive`. */
  startDemoDrive(): void;
  stopDemoDrive(): void;
  /** Development: restart the replay and wait for the Kerrville crest, then return to a calm picture. */
  resetDemo(): Promise<void>;
  /** Development: make writes fail. Reflected in `connection.failWrites` so the UI re-renders. */
  setSimulateFailures(enabled: boolean): void;
  readonly simulateFailures: boolean;
}

export class RepositoryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RepositoryError';
  }
}

/** A map point is usable when both parts are finite and within ±180 longitude / ±90 latitude. */
export function isValidLngLat(p: readonly unknown[]): p is LngLat {
  const [lon, lat] = p;
  return (
    p.length === 2 &&
    typeof lon === 'number' &&
    typeof lat === 'number' &&
    Number.isFinite(lon) &&
    Number.isFinite(lat) &&
    Math.abs(lon) <= 180 &&
    Math.abs(lat) <= 90
  );
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
