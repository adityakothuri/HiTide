import type { AppState, AssistantLine, DangerLevel, EmergencyContact, LngLat, Preferences, RouteId, Scenario } from '@/domain/types';
import { distanceM } from '@/domain/routeGeometry';
import { initialState } from '@/state/reducer';
import { sampleDirections } from './fixtures';
import { type HiTideRepository, isValidLngLat, RepositoryError, validateContact } from './repository';
import { AppStore, type KeyValueStore, STORAGE_KEY } from './store';

export { type KeyValueStore, STORAGE_KEY };

export interface MockOptions {
  storage: KeyValueStore;
  /** Simulated network latency for writes, in ms. */
  latencyMs?: number;
  /** Delay before the simulated emergency-contact notification. */
  contactNotifyDelayMs?: number;
  now?: () => string;
}

const DEFAULT_LATENCY_MS = 250;
/** Sample mode: a pin this close to sample flooding gets a warning with directions. */
const SAMPLE_NEAR_FLOOD_M = 600;

/** The level a backend might give a pin, judged against the sample flood picture. Never danger: no call in sample mode. */
function sampleLevel(state: AppState, at: LngLat): DangerLevel {
  const layer = state.floodLayer;
  if (!layer) return 'none';
  const wet = [
    ...layer.points.filter((p) => p.status !== 'open' && p.status !== 'unknown').map((p) => p.at),
    ...layer.roads.filter((r) => r.status === 'confirmed_flooded' || r.status === 'likely_flooded').flatMap((r) => r.coords),
  ];
  if (wet.some((p) => distanceM(p, at) <= SAMPLE_NEAR_FLOOD_M)) return 'warning';
  return state.warning ? 'watch' : 'none';
}
const DEFAULT_CONTACT_NOTIFY_MS = 1800;

/** Local, deterministic implementation of the data boundary. No network, no real outreach. */
export class MockHiTideRepository implements HiTideRepository {
  readonly supportsDemoDrive = false;
  private readonly store: AppStore;
  private readonly timers = new Set<ReturnType<typeof setTimeout>>();
  private readonly latencyMs: number;
  private readonly contactNotifyDelayMs: number;
  private readonly now: () => string;
  private helpInFlight = false;

  constructor(opts: MockOptions) {
    this.latencyMs = opts.latencyMs ?? DEFAULT_LATENCY_MS;
    this.contactNotifyDelayMs = opts.contactNotifyDelayMs ?? DEFAULT_CONTACT_NOTIFY_MS;
    this.now = opts.now ?? (() => new Date().toISOString());
    this.store = new AppStore(initialState(this.now()), opts.storage);
  }

  get simulateFailures(): boolean {
    return this.getSnapshot().connection.failWrites;
  }

  load(): Promise<void> {
    return this.store.hydrate(this.now());
  }

  start(): void {
    // Sample data has no background work.
  }

  stop(): void {
    this.clearTimers();
  }

  getSnapshot = (): AppState => this.store.getSnapshot();

  subscribe = (listener: () => void): (() => void) => this.store.subscribe(listener);

  async selectRoute(routeId: RouteId): Promise<void> {
    await this.write();
    this.store.dispatch({ type: 'select_route', routeId, now: this.now() });
  }

  async chooseRoute(choiceId: string): Promise<void> {
    await this.write();
    this.store.dispatch({ type: 'choose_route', id: choiceId, now: this.now() });
  }

  markRead(updateId: string): void {
    this.store.dispatch({ type: 'mark_read', id: updateId });
  }

  async updateContact(contact: EmergencyContact): Promise<void> {
    const trimmed = { name: contact.name.trim(), relationship: contact.relationship.trim(), phone: contact.phone.trim() };
    if (!validateContact(trimmed).ok) throw new RepositoryError('Check the contact details and try again.');
    await this.write();
    this.store.dispatch({ type: 'update_contact', contact: trimmed });
  }

  async setPreferences(patch: Partial<Preferences>): Promise<void> {
    this.store.dispatch({ type: 'set_preferences', patch });
  }

  acknowledgeTurnAround(): void {
    this.store.dispatch({ type: 'acknowledge_turn_around', now: this.now() });
  }

  async markSafe(): Promise<void> {
    await this.write();
    this.store.dispatch({ type: 'mark_safe', now: this.now() });
  }

  async requestHelp(): Promise<void> {
    if (this.helpInFlight || this.getSnapshot().safetyCase?.status !== 'checking') return;
    this.helpInFlight = true;
    try {
      await this.write();
      this.store.dispatch({ type: 'request_help', now: this.now() });
      this.later(this.contactNotifyDelayMs, () => this.store.dispatch({ type: 'contact_notified', now: this.now() }));
    } finally {
      this.helpInFlight = false;
    }
  }

  async callAssistant(): Promise<AssistantLine> {
    await this.write();
    const line: AssistantLine = { mode: 'mock', phone: null, requestedAt: this.now() };
    this.store.dispatch({ type: 'assistant_requested', line });
    return line;
  }

  async setLocation(at: LngLat): Promise<void> {
    if (!isValidLngLat(at)) throw new RepositoryError('That location isn’t on the map. Try again.');
    await this.write();
    const level = sampleLevel(this.getSnapshot(), at);
    const directions = level === 'warning' ? sampleDirections() : null;
    this.store.dispatch({ type: 'pin_location', at, now: this.now(), sample: { level, directions } });
  }

  minimizeCase(): void {
    this.store.dispatch({ type: 'minimize_case' });
  }

  restoreCase(): void {
    this.store.dispatch({ type: 'restore_case' });
  }

  dismissResolved(): void {
    this.store.dispatch({ type: 'dismiss_resolved' });
  }

  setScenario(scenario: Scenario): void {
    this.clearTimers();
    this.store.dispatch({ type: 'set_scenario', scenario, now: this.now() });
  }

  async reset(): Promise<void> {
    this.clearTimers();
    await this.store.clearPersisted();
    this.store.dispatch({ type: 'reset', now: this.now() });
  }

  startDemoDrive(): void {
    // Sample-data mode has no backend to ping; the scenario controls cover every state.
  }

  resetDemo(): Promise<void> {
    return this.reset();
  }

  stopDemoDrive(): void {
    // Nothing to stop in sample-data mode.
  }

  setSimulateFailures(enabled: boolean): void {
    this.store.dispatch({ type: 'set_connection', patch: { failWrites: enabled } });
  }

  /** Simulates a network round trip and the optional failure mode. */
  private async write(): Promise<void> {
    if (this.latencyMs > 0) await new Promise<void>((resolve) => setTimeout(resolve, this.latencyMs));
    if (this.simulateFailures) throw new RepositoryError('Couldn’t reach HiTide. Check your connection and try again.');
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
