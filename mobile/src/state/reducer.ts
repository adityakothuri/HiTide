import {
  sampleRouteChoices,
  sampleDirections,
  sampleFloodLayer,
  DEFAULT_CONTACT,
  DEFAULT_PREFERENCES,
  DEMO_USER,
  UPDATE_IDS,
  buildTrip,
  buildGauge,
  buildWarning,
  contactUpdate,
  routeChangedUpdate,
  warningUpdate,
} from '@/data/fixtures';
import { applyAssessment } from '@/data/live/mapAssessment';
import type { Assessment } from '@/data/live/schema';
import { caseUpdate, routeSelectedUpdate, turnAroundUpdate } from './updates';
import type {
  AppState,
  AssistantLine,
  Connection,
  DangerLevel,
  Directions,
  LngLat,
  FloodLayer,
  RouteChoice,
  CaseEvent,
  EmergencyContact,
  FlowMode,
  GaugeReading,
  PersistedState,
  Preferences,
  RouteId,
  SafetyCase,
  Scenario,
  TurnAroundAlert,
  UpdateItem,
} from '@/domain/types';

export type Action =
  | { type: 'hydrate'; persisted: PersistedState; now: string }
  | { type: 'set_scenario'; scenario: Scenario; now: string }
  | { type: 'select_route'; routeId: RouteId; now: string }
  | { type: 'mark_read'; id: string }
  | { type: 'update_contact'; contact: EmergencyContact }
  | { type: 'set_preferences'; patch: Partial<Preferences> }
  | { type: 'acknowledge_turn_around'; now: string }
  | { type: 'mark_safe'; now: string }
  | { type: 'request_help'; now: string }
  | { type: 'contact_notified'; now: string }
  | { type: 'minimize_case' }
  | { type: 'restore_case' }
  | { type: 'dismiss_resolved' }
  | { type: 'reset'; now: string }
  | { type: 'apply_remote'; assessment: Assessment }
  | { type: 'set_gauge'; gauge: GaugeReading }
  | { type: 'set_connection'; patch: Partial<Connection> }
  | { type: 'set_flood_layer'; layer: FloodLayer }
  | { type: 'set_directions'; directions: Directions | null }
  | { type: 'assistant_requested'; line: AssistantLine }
  | { type: 'set_route_choices'; choices: readonly RouteChoice[] }
  | { type: 'choose_route'; id: string; now: string }
  /** A pin dropped on the map. `sample` (mock mode only) supplies the level and directions a backend would give. */
  | { type: 'pin_location'; at: LngLat; now: string; sample?: { level: DangerLevel; directions: Directions | null } };

export const DEFAULT_SCENARIO: Scenario = 'flood_warning';

export const MOCK_CONNECTION: Connection = {
  kind: 'mock',
  status: 'live',
  mode: null,
  assessedAt: null,
  level: null,
  drive: 'idle',
  paused: false,
  failWrites: false,
  degraded: false,
  topReason: null,
  callPlaced: false,
  lastOutreach: null,
};

/** A replay restart rewinds the clock by hours; a late poll is only seconds to minutes old. */
const REWIND_MS = 60 * 60 * 1000;

/** True when this assessment is older than the one already shown, and not a replay rewind. */
function isStale(state: AppState, assessment: Assessment): boolean {
  const shown = state.connection.assessedAt;
  if (!shown) return false;
  const age = Date.parse(shown) - Date.parse(assessment.assessed_at);
  return age > 0 && age < REWIND_MS;
}

function patchConnection(state: AppState, patch: Partial<Connection>): AppState {
  const keys = Object.keys(patch) as (keyof Connection)[];
  if (keys.every((k) => patch[k] === undefined || state.connection[k] === patch[k])) return state;
  const defined = Object.fromEntries(Object.entries(patch).filter(([, v]) => v !== undefined));
  return { ...state, connection: { ...state.connection, ...defined } };
}

interface Carry {
  contact: EmergencyContact;
  preferences: Preferences;
  selectedRouteId: RouteId;
  readIds: readonly string[];
}

const DEFAULT_CARRY: Carry = {
  contact: DEFAULT_CONTACT,
  preferences: DEFAULT_PREFERENCES,
  selectedRouteId: 'original',
  readIds: [],
};

const CASE_LOCATION_LABEL = 'Riverside Drive';

function makeAlert(now: string): TurnAroundAlert {
  return {
    id: `alert-${now}`,
    road: 'Riverside Drive',
    message: 'Flooded road ahead. Turn around.',
    spokenText: 'Flooded road ahead on Riverside Drive. Turn around. Do not drive through floodwater.',
    issuedAt: now,
    acknowledged: false,
  };
}

function makeCase(status: SafetyCase['status'], now: string): SafetyCase {
  const events: CaseEvent[] = [{ kind: 'stop_detected', at: now, simulated: true }];
  if (status === 'help_requested') {
    events.push({ kind: 'help_received', at: now, simulated: true });
    events.push({ kind: 'contact_notified', at: now, simulated: true });
  }
  if (status === 'safe') events.push({ kind: 'marked_safe', at: now, simulated: false });
  return {
    id: `case-${now}`,
    status,
    locationLabel: CASE_LOCATION_LABEL,
    location: [-99.1209, 30.0157],
    openedAt: now,
    events,
    minimized: false,
  };
}

/** Builds a complete, reviewable state for a scenario while keeping the user's own settings. */
export function buildScenario(
  scenario: Scenario,
  carry: Carry,
  now: string,
  connection: Connection = MOCK_CONNECTION,
): AppState {
  const trip = buildTrip(now);
  const hasWarning = scenario !== 'normal';
  const updates: UpdateItem[] = [contactUpdate(now, carry.contact.name)];
  if (hasWarning) updates.push(warningUpdate(now), routeChangedUpdate(now));

  let selectedRouteId = hasWarning ? carry.selectedRouteId : 'original';
  let alert: TurnAroundAlert | null = null;
  let safetyCase: SafetyCase | null = null;

  if (scenario === 'alternate_route') selectedRouteId = 'alternate';
  if (selectedRouteId === 'alternate') updates.push(routeSelectedUpdate(now, trip.routes.alternate.via));
  if (scenario === 'turn_around') {
    selectedRouteId = 'original';
    alert = makeAlert(now);
    updates.push(turnAroundUpdate(now, 'Riverside Drive'));
  }
  if (scenario === 'check_in') {
    safetyCase = makeCase('checking', now);
    updates.push(caseUpdate('check_in', now));
  }
  if (scenario === 'help_requested') {
    safetyCase = makeCase('help_requested', now);
    updates.push(caseUpdate('check_in', now), caseUpdate('help', now));
  }
  if (scenario === 'resolved') {
    safetyCase = makeCase('safe', now);
    updates.push(caseUpdate('check_in', now), caseUpdate('safe', now));
  }

  return {
    scenario,
    user: DEMO_USER,
    contact: carry.contact,
    preferences: carry.preferences,
    trip: hasWarning ? trip : { ...trip, closure: null },
    selectedRouteId,
    warning: hasWarning ? buildWarning(now) : null,
    gauge: buildGauge(now, hasWarning),
    updates,
    readIds: carry.readIds,
    alert,
    safetyCase,
    position: null,
    // Sample mode draws an illustrative flood picture; live mode fills these from the backend.
    floodLayer: connection.kind === 'mock' && hasWarning ? sampleFloodLayer(now) : null,
    directions: connection.kind === 'mock' && safetyCase ? sampleDirections() : null,
    assistant: null,
    lastPin: null,
    routeChoices: connection.kind === 'mock' && hasWarning ? sampleRouteChoices(trip) : [],
    selectedChoiceId: connection.kind === 'mock' && hasWarning ? selectedRouteId : null,
    connection,
  };
}

export function initialState(now: string): AppState {
  return buildScenario(DEFAULT_SCENARIO, DEFAULT_CARRY, now);
}

/** Live mode starts calm and waits for the backend: no sample warning, closure, or case. */
export function liveInitialState(now: string): AppState {
  return buildScenario('normal', DEFAULT_CARRY, now, { ...MOCK_CONNECTION, kind: 'live', status: 'connecting' });
}

const resetScenario = (state: AppState): Scenario => (state.connection.kind === 'live' ? 'normal' : DEFAULT_SCENARIO);

const carryFrom = (s: AppState): Carry => ({
  contact: s.contact,
  preferences: s.preferences,
  selectedRouteId: s.selectedRouteId,
  readIds: s.readIds,
});

const withUpdate = (updates: readonly UpdateItem[], item: UpdateItem): UpdateItem[] => [
  ...updates.filter((u) => u.id !== item.id),
  item,
];

const unread = (ids: readonly string[], id: string): string[] => ids.filter((x) => x !== id);

function selectRoute(state: AppState, routeId: RouteId, now: string): AppState {
  if (routeId === 'alternate' && !state.trip.closure) return state;
  const updates =
    routeId === 'alternate'
      ? withUpdate(state.updates, routeSelectedUpdate(now, state.trip.routes.alternate.via))
      : state.updates.filter((u) => u.id !== UPDATE_IDS.routeSelected);
  const readIds = routeId === 'alternate' ? unread(state.readIds, UPDATE_IDS.routeSelected) : state.readIds;
  return { ...state, selectedRouteId: routeId, updates, readIds };
}

function addCaseEvent(c: SafetyCase, event: CaseEvent): SafetyCase {
  return { ...c, events: [...c.events, event] };
}

/** A scenario rebuild keeps the live map picture: it comes from the backend, not from the scenario. */
function keepLive(prev: AppState, next: AppState): AppState {
  return prev.connection.kind === 'live'
    ? {
        ...next,
        floodLayer: prev.floodLayer,
        routeChoices: prev.routeChoices,
        selectedChoiceId: prev.selectedChoiceId,
        lastPin: prev.lastPin,
      }
    : next;
}

function pinLocation(state: AppState, action: Extract<Action, { type: 'pin_location' }>): AppState {
  const level = action.sample ? action.sample.level : state.connection.level;
  const lastPin = { at: action.at, level, requestedAt: action.now };
  if (!action.sample) return { ...state, position: action.at, lastPin };
  return {
    ...state,
    position: action.at,
    lastPin,
    directions: action.sample.directions,
    connection: { ...state.connection, level },
  };
}

const ASSISTANT_DETAIL: Record<AssistantLine['mode'], string> = {
  live: 'Calling the HiTide assistant',
  mock: 'Simulated call',
  unavailable: 'Assistant line unavailable',
};

function requestAssistant(state: AppState, line: AssistantLine): AppState {
  const c = state.safetyCase;
  if (!c) return { ...state, assistant: line };
  const event: CaseEvent = {
    kind: 'assistant_call',
    at: line.requestedAt,
    simulated: line.mode !== 'live',
    detail: ASSISTANT_DETAIL[line.mode],
  };
  return { ...state, assistant: line, safetyCase: { ...c, events: [...c.events.filter((e) => e.kind !== 'assistant_call'), event] } };
}

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'hydrate': {
      const p = action.persisted;
      return keepLive(
        state,
        buildScenario(
          state.scenario,
          { contact: p.contact, preferences: p.preferences, selectedRouteId: p.selectedRouteId, readIds: p.readIds },
          action.now,
          state.connection,
        ),
      );
    }
    case 'set_scenario':
      return keepLive(state, buildScenario(action.scenario, carryFrom(state), action.now, state.connection));
    case 'reset':
      return { ...keepLive(state, buildScenario(resetScenario(state), DEFAULT_CARRY, action.now, state.connection)), lastPin: null };
    case 'pin_location':
      return pinLocation(state, action);
    case 'set_flood_layer':
      return state.floodLayer === action.layer ? state : { ...state, floodLayer: action.layer };
    case 'set_directions':
      return state.directions === action.directions ? state : { ...state, directions: action.directions };
    case 'assistant_requested':
      return requestAssistant(state, action.line);
    case 'set_route_choices': {
      const keep = action.choices.some((c) => c.id === state.selectedChoiceId);
      return { ...state, routeChoices: action.choices, selectedChoiceId: keep ? state.selectedChoiceId : null };
    }
    case 'choose_route': {
      if (!state.routeChoices.some((c) => c.id === action.id)) return state;
      const chosen = { ...state, selectedChoiceId: action.id };
      // Sample-mode choices are the fixture routes: keep the route-update flow in step.
      return action.id === 'original' || action.id === 'alternate' ? selectRoute(chosen, action.id, action.now) : chosen;
    }
    case 'apply_remote':
      return state.connection.paused || isStale(state, action.assessment) ? state : applyAssessment(state, action.assessment);
    case 'set_gauge':
      return state.connection.paused || state.gauge === action.gauge ? state : { ...state, gauge: action.gauge };
    case 'set_connection':
      return patchConnection(state, action.patch);
    case 'select_route':
      return selectRoute(state, action.routeId, action.now);
    case 'mark_read':
      return state.readIds.includes(action.id) ? state : { ...state, readIds: [...state.readIds, action.id] };
    case 'update_contact': {
      const updates = state.updates.map((u) =>
        u.id === UPDATE_IDS.contact ? { ...u, body: `${action.contact.name} is your emergency contact` } : u,
      );
      return { ...state, contact: action.contact, updates };
    }
    case 'set_preferences':
      return { ...state, preferences: { ...state.preferences, ...action.patch } };
    case 'acknowledge_turn_around': {
      if (!state.alert || state.alert.acknowledged) return state;
      const next = selectRoute(state, 'alternate', action.now);
      return { ...next, alert: { ...state.alert, acknowledged: true } };
    }
    case 'request_help': {
      const c = state.safetyCase;
      if (!c || c.status !== 'checking') return state;
      const received = addCaseEvent(c, { kind: 'help_received', at: action.now, simulated: true });
      return {
        ...state,
        safetyCase: { ...received, status: 'help_requested', minimized: false },
        updates: withUpdate(state.updates, caseUpdate('help', action.now)),
      };
    }
    case 'contact_notified': {
      const c = state.safetyCase;
      if (!c || c.status !== 'help_requested' || c.events.some((e) => e.kind === 'contact_notified')) return state;
      return { ...state, safetyCase: addCaseEvent(c, { kind: 'contact_notified', at: action.now, simulated: true }) };
    }
    case 'mark_safe': {
      const c = state.safetyCase;
      if (!c || c.status === 'safe') return state;
      const marked = addCaseEvent(c, { kind: 'marked_safe', at: action.now, simulated: false });
      return {
        ...state,
        safetyCase: { ...marked, status: 'safe', minimized: false },
        updates: withUpdate(state.updates, caseUpdate('safe', action.now)),
      };
    }
    case 'minimize_case':
      return state.safetyCase ? { ...state, safetyCase: { ...state.safetyCase, minimized: true } } : state;
    case 'restore_case':
      return state.safetyCase ? { ...state, safetyCase: { ...state.safetyCase, minimized: false } } : state;
    case 'dismiss_resolved':
      return state.safetyCase?.status === 'safe' ? { ...state, safetyCase: null } : state;
    default:
      return state;
  }
}

/** Which focused flow to show. Precedence: safety case > turn-around alert > ordinary tabs. */
export function deriveFlowMode(state: AppState): FlowMode {
  const c = state.safetyCase;
  if (c) {
    if (c.status === 'checking') return 'check_in';
    if (c.minimized) return 'normal';
    return c.status === 'help_requested' ? 'support' : 'resolved';
  }
  if (state.alert && !state.alert.acknowledged) return 'turn_around';
  return 'normal';
}

export function toPersisted(state: AppState): PersistedState {
  return {
    version: 1,
    contact: state.contact,
    preferences: state.preferences,
    selectedRouteId: state.selectedRouteId,
    readIds: state.readIds,
  };
}
