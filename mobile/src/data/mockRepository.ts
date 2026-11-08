import type { AppState, EmergencyContact, PersistedState, Preferences, RouteId, Scenario } from '@/domain/types';
import { type Action, initialState, reducer, toPersisted } from '@/state/reducer';
import { type HiTideRepository, RepositoryError, validateContact } from './repository';

export interface KeyValueStore {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export interface MockOptions {
  storage: KeyValueStore;
  /** Simulated network latency for writes, in ms. */
  latencyMs?: number;
  /** Delay before the simulated emergency-contact notification. */
  contactNotifyDelayMs?: number;
  now?: () => string;
}

export const STORAGE_KEY = 'hitide/state/v1';
const DEFAULT_LATENCY_MS = 250;
const DEFAULT_CONTACT_NOTIFY_MS = 1800;

function isPersisted(value: unknown): value is PersistedState {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<PersistedState>;
  return (
    v.version === 1 &&
    typeof v.contact?.name === 'string' &&
    typeof v.contact?.phone === 'string' &&
    typeof v.preferences?.spokenAlerts === 'boolean' &&
    typeof v.preferences?.locationSharing === 'boolean' &&
    (v.selectedRouteId === 'original' || v.selectedRouteId === 'alternate') &&
    Array.isArray(v.readIds)
  );
}

/** Local, deterministic implementation of the data boundary. No network, no real outreach. */
export class MockHiTideRepository implements HiTideRepository {
  private state: AppState;
  private readonly listeners = new Set<() => void>();
  private readonly timers = new Set<ReturnType<typeof setTimeout>>();
  private readonly storage: KeyValueStore;
  private readonly latencyMs: number;
  private readonly contactNotifyDelayMs: number;
  private readonly now: () => string;
  private helpInFlight = false;
  private failNextWrites = false;

  constructor(opts: MockOptions) {
    this.storage = opts.storage;
    this.latencyMs = opts.latencyMs ?? DEFAULT_LATENCY_MS;
    this.contactNotifyDelayMs = opts.contactNotifyDelayMs ?? DEFAULT_CONTACT_NOTIFY_MS;
    this.now = opts.now ?? (() => new Date().toISOString());
    this.state = initialState(this.now());
  }

  get simulateFailures(): boolean {
    return this.failNextWrites;
  }

  async load(): Promise<void> {
    try {
      const raw = await this.storage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed: unknown = JSON.parse(raw);
      if (isPersisted(parsed)) this.dispatch({ type: 'hydrate', persisted: parsed, now: this.now() });
    } catch {
      // Corrupt or unreadable storage: keep defaults rather than blocking the app.
    }
  }

  getSnapshot = (): AppState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  async selectRoute(routeId: RouteId): Promise<void> {
    await this.write();
    this.dispatch({ type: 'select_route', routeId, now: this.now() });
  }

  markRead(updateId: string): void {
    this.dispatch({ type: 'mark_read', id: updateId });
  }

  async updateContact(contact: EmergencyContact): Promise<void> {
    const trimmed = { name: contact.name.trim(), relationship: contact.relationship.trim(), phone: contact.phone.trim() };
    if (!validateContact(trimmed).ok) throw new RepositoryError('Check the contact details and try again.');
    await this.write();
    this.dispatch({ type: 'update_contact', contact: trimmed });
  }

  async setPreferences(patch: Partial<Preferences>): Promise<void> {
    this.dispatch({ type: 'set_preferences', patch });
  }

  acknowledgeTurnAround(): void {
    this.dispatch({ type: 'acknowledge_turn_around', now: this.now() });
  }

  async markSafe(): Promise<void> {
    await this.write();
    this.dispatch({ type: 'mark_safe', now: this.now() });
  }

  async requestHelp(): Promise<void> {
    if (this.helpInFlight || this.state.safetyCase?.status !== 'checking') return;
    this.helpInFlight = true;
    try {
      await this.write();
      this.dispatch({ type: 'request_help', now: this.now() });
      this.later(this.contactNotifyDelayMs, () => this.dispatch({ type: 'contact_notified', now: this.now() }));
    } finally {
      this.helpInFlight = false;
    }
  }

  minimizeCase(): void {
    this.dispatch({ type: 'minimize_case' });
  }

  restoreCase(): void {
    this.dispatch({ type: 'restore_case' });
  }

  dismissResolved(): void {
    this.dispatch({ type: 'dismiss_resolved' });
  }

  setScenario(scenario: Scenario): void {
    this.clearTimers();
    this.dispatch({ type: 'set_scenario', scenario, now: this.now() });
  }

  async reset(): Promise<void> {
    this.clearTimers();
    try {
      await this.storage.removeItem(STORAGE_KEY);
    } catch {
      // Reset still restores in-memory defaults.
    }
    this.dispatch({ type: 'reset', now: this.now() });
  }

  setSimulateFailures(enabled: boolean): void {
    this.failNextWrites = enabled;
    this.emit();
  }

  dispose(): void {
    this.clearTimers();
    this.listeners.clear();
  }

  private dispatch(action: Action): void {
    const next = reducer(this.state, action);
    if (next === this.state) return;
    const persistChanged = JSON.stringify(toPersisted(next)) !== JSON.stringify(toPersisted(this.state));
    this.state = next;
    if (persistChanged) void this.persist();
    this.emit();
  }

  private emit(): void {
    this.listeners.forEach((l) => l());
  }

  private async persist(): Promise<void> {
    try {
      await this.storage.setItem(STORAGE_KEY, JSON.stringify(toPersisted(this.state)));
    } catch {
      // Persistence is best-effort for the demo; in-memory state stays correct.
    }
  }

  /** Simulates a network round trip and the optional failure mode. */
  private async write(): Promise<void> {
    if (this.latencyMs > 0) await new Promise<void>((resolve) => setTimeout(resolve, this.latencyMs));
    if (this.failNextWrites) throw new RepositoryError('Couldn’t reach HiTide. Check your connection and try again.');
  }

  private later(ms: number, fn: () => void): void {
    const t = setTimeout(() => {
      this.timers.delete(t);
      fn();
    }, ms);
    this.timers.add(t);
  }

  private clearTimers(): void {
    this.timers.forEach(clearTimeout);
    this.timers.clear();
  }
}
