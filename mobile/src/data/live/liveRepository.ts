import type { AppState, AssistantLine, EmergencyContact, LngLat, Preferences, RouteId, Scenario } from '@/domain/types';
import { liveInitialState } from '@/state/reducer';
import { type HiTideRepository, isValidLngLat, RepositoryError, validateContact } from '../repository';
import { AppStore, type KeyValueStore } from '../store';
import type { LiveConfig } from './config';
import { buildDrivePlan } from './demoDrive';
import { toDirections, toFloodLayer, toRouteChoices } from './mapFlood';
import { toGauge } from './mapGauge';
import {
  isDangerEventFor,
  parseAssessment,
  parseAssistant,
  parseDirections,
  parseFloodLayer,
  parseGauges,
  parseRouteOptions,
  parseSummary,
} from './schema';
import { connectEvents, createDangerApi, type DangerApi, type EventHandlers, HttpError, type LocationPing } from './transport';

export interface LiveOptions {
  config: LiveConfig;
  storage: KeyValueStore;
  api?: DangerApi;
  /** Injected in tests. Defaults to a real WebSocket with reconnect. */
  connect?: (url: string, handlers: EventHandlers) => () => void;
  pollMs?: number;
  gaugePollMs?: number;
  drivePingMs?: number;
  /** How often resetDemo checks whether the replay has reached the crest. */
  crestPollMs?: number;
  now?: () => string;
}

const POLL_MS = 5000;
const GAUGE_POLL_MS = 30_000;
const FLOOD_POLL_MS = 15_000;
/** Directions are recomputed at most this often while a check-in or help case is open. */
const DIRECTIONS_MAX_AGE_MS = 20_000;
/** The phone's map window: Kerrville and the Guadalupe River (matches the Home overview). */
export const KERRVILLE_BBOX = '-99.18,29.99,-99.08,30.08';
const DRIVE_PING_MS = 1500;
const CREST_POLL_MS = 2000;
/** On the replay clock: Park Street at Quinlan Creek is confirmed flooded from about here (07:10 CDT). */
const CREST_AT = '2025-07-04T12:10:00Z';
const CREST_TIMEOUT_MS = 150_000;
const REPLAY_LABEL = 'replay of July 4, 2025';
const UNREACHABLE = 'Couldn’t reach HiTide. Check your connection and try again.';
const REJECTED = 'HiTide couldn’t accept that. Try again.';
/** After Set location, these levels come with directions (the result screen shows them). */
const PIN_DIRECTION_LEVELS = new Set<string>(['warning', 'danger', 'critical']);
const BACKEND_NOT_READY = 409;
const FIRST_SERVER_ERROR = 500;

/** Network errors, timeouts and 5xx mean "can't reach HiTide". A 4xx is a request problem, not an outage. */
function isOutage(e: unknown): boolean {
  return !(e instanceof HttpError) || e.status >= FIRST_SERVER_ERROR;
}

/**
 * The backend-backed data boundary. Reads the user's danger assessment (poll + WebSocket nudge), writes replies,
 * planned routes, and demo-drive location pings. Contact and preferences stay on the device.
 */
export class LiveHiTideRepository implements HiTideRepository {
  readonly supportsDemoDrive = true;
  private readonly store: AppStore;
  private readonly api: DangerApi;
  private readonly config: LiveConfig;
  private readonly connect: (url: string, handlers: EventHandlers) => () => void;
  private readonly now: () => string;
  private readonly pollMs: number;
  private readonly gaugePollMs: number;
  private readonly drivePingMs: number;
  private readonly crestPollMs: number;
  private readonly intervals = new Set<ReturnType<typeof setInterval>>();
  private loading: Promise<void> | null = null;
  private running = false;
  private stopEvents: (() => void) | null = null;
  private driveTimer: ReturnType<typeof setTimeout> | null = null;
  /** Incremented on every drive start/stop, so a ping that resolves late can't continue an old drive. */
  private driveRun = 0;
  private refreshing: Promise<void> | null = null;
  private lastRaw: string | null = null;
  private helpInFlight = false;
  private assistantInFlight: Promise<AssistantLine> | null = null;
  private directionsAt = 0;
  private lastFloodRaw: string | null = null;
  private lastDirectionsRaw: string | null = null;
  private lastRoutesRaw: string | null = null;

  constructor(opts: LiveOptions) {
    this.config = opts.config;
    this.api = opts.api ?? createDangerApi(opts.config);
    this.connect = opts.connect ?? connectEvents;
    this.now = opts.now ?? (() => new Date().toISOString());
    this.pollMs = opts.pollMs ?? POLL_MS;
    this.gaugePollMs = opts.gaugePollMs ?? GAUGE_POLL_MS;
    this.drivePingMs = opts.drivePingMs ?? DRIVE_PING_MS;
    this.crestPollMs = opts.crestPollMs ?? CREST_POLL_MS;
    this.store = new AppStore(liveInitialState(this.now()), opts.storage);
  }

  get simulateFailures(): boolean {
    return this.getSnapshot().connection.failWrites;
  }

  getSnapshot = (): AppState => this.store.getSnapshot();

  subscribe = (listener: () => void): (() => void) => this.store.subscribe(listener);

  /** Restores local settings once. Network work begins in start(). */
  load(): Promise<void> {
    this.loading ??= this.store.hydrate(this.now());
    return this.loading;
  }

  // ---- lifecycle --------------------------------------------------------------------------------

  start(): void {
    if (this.running) return;
    this.running = true;
    void this.refreshAll();
    this.intervals.add(setInterval(() => void this.refresh(), this.pollMs));
    this.intervals.add(setInterval(() => void this.refreshContext(), this.gaugePollMs));
    this.intervals.add(setInterval(() => void this.refreshRoutes(), this.gaugePollMs));
    this.intervals.add(setInterval(() => void this.refreshFlood(), FLOOD_POLL_MS));
    this.stopEvents = this.connect(this.config.wsUrl, {
      onMessage: (data) => {
        if (isDangerEventFor(data, this.config.userId)) void this.refresh(true);
      },
      onOpen: () => void this.refresh(),
      onClose: () => undefined, // polling keeps working; the badge reflects HTTP reachability
    });
    // Pre-trip check: the backend checks every road on the planned route.
    void this.checkRoute(this.getSnapshot().selectedRouteId).catch(() => undefined);
  }

  stop(): void {
    this.running = false;
    this.intervals.forEach(clearInterval);
    this.intervals.clear();
    this.stopEvents?.();
    this.stopEvents = null;
    this.stopDemoDrive();
  }

  // ---- reads ------------------------------------------------------------------------------------

  private async refreshAll(): Promise<void> {
    await this.refreshContext();
    await this.refreshFlood();
    await this.refreshRoutes();
    await this.refresh();
  }

  /**
   * Fetches the assessment. Overlapping calls share one request; `fresh` waits for any in-flight request and then
   * fetches again, so a read issued after a write never reuses a response that started before it.
   */
  private refresh(fresh = false): Promise<void> {
    if (!this.running) return Promise.resolve();
    if (this.refreshing && fresh) return this.refreshing.then(() => this.refresh());
    this.refreshing ??= this.fetchAssessment().finally(() => {
      this.refreshing = null;
    });
    return this.refreshing;
  }

  private async fetchAssessment(): Promise<void> {
    try {
      this.applyRemote(await this.api.getDanger());
    } catch (e) {
      this.noteReadFailure(e);
      return;
    }
    await this.refreshDirections();
  }

  /** The flood layers for the map. Best effort: the danger poll alone decides whether the app is live. */
  private async refreshFlood(): Promise<void> {
    if (!this.running) return;
    try {
      const raw = await this.api.getFloodLayer(KERRVILLE_BBOX);
      const key = JSON.stringify(raw);
      if (key === this.lastFloodRaw) return; // unchanged since the last poll: keep the same object, no redraw
      const layer = parseFloodLayer(raw);
      if (!layer) return;
      this.lastFloodRaw = key;
      this.store.dispatch({ type: 'set_flood_layer', layer: toFloodLayer(layer) });
    } catch {
      // The map keeps its last flood picture; the badge still reflects reachability.
    }
  }

  /** Ways to make the trip, each with the flooding on it. Best effort, refreshed with the gauge. */
  private async refreshRoutes(): Promise<void> {
    if (!this.running) return;
    const { origin, destination } = this.getSnapshot().trip;
    try {
      const raw = await this.api.getRouteOptions(origin, destination);
      const key = JSON.stringify(raw);
      if (key === this.lastRoutesRaw) return;
      const parsed = parseRouteOptions(raw);
      if (!parsed) return;
      this.lastRoutesRaw = key;
      this.store.dispatch({ type: 'set_route_choices', choices: toRouteChoices(parsed) });
    } catch {
      // Keep the last options; the usual / alternate pair still works.
    }
  }

  /**
   * While a check-in or help case is open, or a pin the person set has a warning, keep a fresh way to higher ground
   * for the map and the assistant.
   */
  private async refreshDirections(force = false): Promise<void> {
    const state = this.getSnapshot();
    const pinWarned = state.lastPin !== null && PIN_DIRECTION_LEVELS.has(state.connection.level ?? 'none');
    if (!state.safetyCase && !pinWarned) {
      if (state.directions) this.store.dispatch({ type: 'set_directions', directions: null });
      return;
    }
    if (!force && Date.now() - this.directionsAt < DIRECTIONS_MAX_AGE_MS) return;
    this.directionsAt = Date.now();
    try {
      const raw = await this.api.getDirections();
      const key = JSON.stringify(raw);
      if (key === this.lastDirectionsRaw && this.getSnapshot().directions) return;
      const d = parseDirections(raw);
      if (!d) return;
      this.lastDirectionsRaw = key;
      this.store.dispatch({ type: 'set_directions', directions: toDirections(d) });
    } catch {
      // Keep the last directions; the assistant gives guidance by voice either way.
    }
  }

  /** Backend mode and the river gauge. Best effort: a failure here never marks the app offline. */
  private async refreshContext(): Promise<void> {
    try {
      const summary = parseSummary(await this.api.getSummary());
      if (summary) this.store.dispatch({ type: 'set_connection', patch: { mode: summary.mode } });
      const gauges = parseGauges(await this.api.getGauges());
      const state = this.getSnapshot();
      const label = state.connection.mode === 'replay' ? REPLAY_LABEL : null;
      const gauge = gauges ? toGauge(gauges, state.gauge, label) : null;
      if (gauge) this.store.dispatch({ type: 'set_gauge', gauge });
    } catch {
      // Context is optional; the danger poll alone decides whether the app is live.
    }
  }

  /**
   * Validates and applies an assessment-shaped payload. Invalid payloads are never half-applied, and are reported
   * as offline so a stale picture is never labelled live.
   */
  private applyRemote(raw: unknown): void {
    if (!this.running) return;
    const assessment = parseAssessment(raw);
    if (!assessment) {
      this.store.dispatch({ type: 'set_connection', patch: { status: 'offline' } });
      return;
    }
    const key = JSON.stringify(raw);
    if (key === this.lastRaw && this.getSnapshot().connection.status === 'live') return; // nothing changed
    this.lastRaw = key;
    this.store.dispatch({ type: 'apply_remote', assessment });
  }

  private noteReadFailure(e: unknown): void {
    if (!this.running) return;
    if (e instanceof HttpError && e.status === BACKEND_NOT_READY) {
      this.store.dispatch({ type: 'set_connection', patch: { status: 'connecting' } });
    } else if (isOutage(e)) {
      this.store.dispatch({ type: 'set_connection', patch: { status: 'offline' } });
    }
  }

  // ---- writes -----------------------------------------------------------------------------------

  /** Runs a backend write; failures surface as a RepositoryError with user-facing copy. */
  private async write<T>(op: () => Promise<T>): Promise<T> {
    if (this.simulateFailures) throw new RepositoryError(UNREACHABLE);
    try {
      return await op();
    } catch (e) {
      if (isOutage(e)) {
        this.noteReadFailure(e);
        throw new RepositoryError(UNREACHABLE);
      }
      throw new RepositoryError(REJECTED);
    }
  }

  private checkRoute(routeId: RouteId): Promise<void> {
    return this.write(() => this.api.postRoute(this.getSnapshot().trip.routes[routeId].coords));
  }

  async selectRoute(routeId: RouteId): Promise<void> {
    await this.checkRoute(routeId);
    this.store.dispatch({ type: 'select_route', routeId, now: this.now() });
    void this.refresh(true);
  }

  /** The backend checks every road on the chosen way (pre-trip), then it becomes the selected option. */
  async chooseRoute(choiceId: string): Promise<void> {
    const choice = this.getSnapshot().routeChoices.find((c) => c.id === choiceId);
    if (!choice) throw new RepositoryError(REJECTED);
    await this.write(() => this.api.postRoute(choice.lines.flat()));
    this.store.dispatch({ type: 'choose_route', id: choiceId, now: this.now() });
    void this.refresh(true);
  }

  markRead(updateId: string): void {
    this.store.dispatch({ type: 'mark_read', id: updateId });
  }

  /** Stored on this device. The backend keeps its own enrolled contact; this demo does not change it. */
  async updateContact(contact: EmergencyContact): Promise<void> {
    const trimmed = { name: contact.name.trim(), relationship: contact.relationship.trim(), phone: contact.phone.trim() };
    if (!validateContact(trimmed).ok) throw new RepositoryError('Check the contact details and try again.');
    this.store.dispatch({ type: 'update_contact', contact: trimmed });
  }

  async setPreferences(patch: Partial<Preferences>): Promise<void> {
    this.store.dispatch({ type: 'set_preferences', patch });
  }

  acknowledgeTurnAround(): void {
    this.store.dispatch({ type: 'acknowledge_turn_around', now: this.now() });
    // The alternate is picked locally; ask the backend to check it so a flooded alternate is reported too.
    if (this.getSnapshot().selectedRouteId === 'alternate') {
      void this.checkRoute('alternate')
        .then(() => this.refresh(true))
        .catch(() => undefined); // best effort: the alert was already acknowledged locally
    }
  }

  async markSafe(): Promise<void> {
    await this.write(() => this.api.postReply('safe'));
    this.store.dispatch({ type: 'mark_safe', now: this.now() });
    void this.refresh(true);
  }

  async requestHelp(): Promise<void> {
    if (this.helpInFlight || this.getSnapshot().safetyCase?.status !== 'checking') return;
    this.helpInFlight = true;
    try {
      await this.write(() => this.api.postReply('need_help'));
      this.store.dispatch({ type: 'request_help', now: this.now() });
      void this.refresh(true);
    } finally {
      this.helpInFlight = false;
    }
  }

  /** One request at a time: a double tap gets the same line back. */
  callAssistant(): Promise<AssistantLine> {
    this.assistantInFlight ??= this.prepareAssistant().finally(() => {
      this.assistantInFlight = null;
    });
    return this.assistantInFlight;
  }

  private async prepareAssistant(): Promise<AssistantLine> {
    const raw = await this.write(() => this.api.requestAssistant());
    const parsed = parseAssistant(raw);
    if (!parsed) throw new RepositoryError(REJECTED);
    const line: AssistantLine = { mode: parsed.mode, phone: parsed.phone ?? null, requestedAt: this.now() };
    if (parsed.directions) this.store.dispatch({ type: 'set_directions', directions: toDirections(parsed.directions) });
    this.store.dispatch({ type: 'assistant_requested', line });
    void this.refresh(true);
    return line;
  }

  /** A pin on the map, sent as a stopped location ping. The backend assesses it and runs its outreach ladder. */
  async setLocation(at: LngLat): Promise<void> {
    if (!isValidLngLat(at)) throw new RepositoryError('That location isn’t on the map. Try again.');
    const raw = await this.write(() => this.api.postLocation({ lat: at[1], lon: at[0], speed_mps: 0 }));
    const assessment = parseAssessment(raw);
    if (!assessment) throw new RepositoryError(REJECTED);
    // The person chose this place: follow the backend again even if a developer scenario paused it.
    this.lastRaw = null;
    this.store.dispatch({ type: 'set_connection', patch: { paused: false } });
    this.store.dispatch({ type: 'apply_remote', assessment });
    this.store.dispatch({ type: 'pin_location', at, now: this.now() });
    await this.refreshDirections(true);
    void this.refresh(true);
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

  // ---- development controls ---------------------------------------------------------------------

  /** Shows a reference state. Backend updates pause until Reset, so the state stays reviewable. */
  setScenario(scenario: Scenario): void {
    this.stopDemoDrive();
    this.store.dispatch({ type: 'set_connection', patch: { paused: true } });
    this.store.dispatch({ type: 'set_scenario', scenario, now: this.now() });
  }

  async reset(): Promise<void> {
    this.stopDemoDrive();
    await this.store.clearPersisted();
    this.lastRaw = null;
    this.store.dispatch({ type: 'set_connection', patch: { paused: false } });
    this.store.dispatch({ type: 'reset', now: this.now() });
    await this.refreshAll();
  }

  /** Restarts the replay (which also resets this user's episode on the backend) and waits for the crest. */
  async resetDemo(): Promise<void> {
    this.stopDemoDrive();
    // The replay clock restarts: forget the last assessment time so the new run isn't rejected as stale.
    this.store.dispatch({ type: 'set_connection', patch: { drive: 'preparing', paused: false, assessedAt: null } });
    try {
      await this.write(() => this.api.restartReplay());
      await this.waitForCrest();
    } finally {
      this.lastRaw = null;
      this.store.dispatch({ type: 'set_scenario', scenario: 'normal', now: this.now() });
      this.store.dispatch({ type: 'set_connection', patch: { drive: 'idle' } });
    }
    await this.refreshContext(); // the gauge too: the replay restarted, so the old reading is from another time
    this.lastFloodRaw = null;
    this.lastRoutesRaw = null;
    await this.refreshFlood();
    await this.refreshRoutes();
    await this.refresh(true);
  }

  private async waitForCrest(): Promise<void> {
    const deadline = Date.now() + CREST_TIMEOUT_MS;
    while (Date.now() < deadline) {
      const assessment = parseAssessment(await this.api.getDanger().catch(() => null));
      if (assessment && Date.parse(assessment.assessed_at) >= Date.parse(CREST_AT)) {
        this.store.dispatch({ type: 'apply_remote', assessment });
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, this.crestPollMs));
    }
    throw new RepositoryError('The replay didn’t reach the flood crest in time. Try Reset demo again.');
  }

  startDemoDrive(): void {
    if (this.driveTimer) return;
    const plan = buildDrivePlan(this.getSnapshot().trip.routes.original.coords);
    // Start from a calm picture (keeps contact and preferences); the backend decides everything after this.
    this.lastRaw = null;
    this.store.dispatch({ type: 'set_scenario', scenario: 'normal', now: this.now() });
    this.store.dispatch({ type: 'set_connection', patch: { paused: false, drive: 'driving' } });
    this.driveRun += 1;
    this.driveStep(plan, 0, this.driveRun);
  }

  stopDemoDrive(): void {
    this.driveRun += 1;
    if (this.driveTimer) clearTimeout(this.driveTimer);
    this.driveTimer = null;
    this.store.dispatch({ type: 'set_connection', patch: { drive: 'idle' } });
  }

  /** Sends one ping, applies the assessment it returns, then schedules the next. Sequential: no overlap. */
  private driveStep(plan: readonly LocationPing[], i: number, run: number): void {
    const ping = plan[i];
    if (!ping) {
      this.driveTimer = null;
      this.store.dispatch({ type: 'set_connection', patch: { drive: 'stopped' } });
      return;
    }
    this.driveTimer = setTimeout(async () => {
      try {
        const result = await this.api.postLocation(ping);
        if (run !== this.driveRun) return; // stopped or restarted while this ping was in flight
        this.applyAssessmentAlways(result);
        this.driveStep(plan, i + 1, run);
      } catch (e) {
        if (run !== this.driveRun) return;
        this.noteReadFailure(e);
        this.stopDemoDrive();
      }
    }, i === 0 ? 0 : this.drivePingMs);
  }

  /** Drive pings must apply even when the repository isn't polling (e.g. tests, or between start/stop). */
  private applyAssessmentAlways(raw: unknown): void {
    const assessment = parseAssessment(raw);
    if (assessment) this.store.dispatch({ type: 'apply_remote', assessment });
  }

  setSimulateFailures(enabled: boolean): void {
    this.store.dispatch({ type: 'set_connection', patch: { failWrites: enabled } });
  }
}
