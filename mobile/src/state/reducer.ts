import {
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
import type {
  AppState,
  CaseEvent,
  EmergencyContact,
  FlowMode,
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
  | { type: 'reset'; now: string };

export const DEFAULT_SCENARIO: Scenario = 'flood_warning';

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

function routeSelectedUpdate(now: string): UpdateItem {
  return {
    id: UPDATE_IDS.routeSelected,
    category: 'trips',
    icon: 'route',
    title: 'Alternate route selected',
    body: 'Your work trip now goes via Memorial Blvd',
    at: now,
    target: 'route',
    actionLabel: 'View route',
  };
}

function turnAroundUpdate(now: string): UpdateItem {
  return {
    id: UPDATE_IDS.turnAround,
    category: 'trips',
    icon: 'warning',
    title: 'Turn-around alert',
    body: 'Flooded road reported ahead on Riverside Drive',
    at: now,
    target: 'route',
    actionLabel: 'Review route',
  };
}

function caseUpdate(kind: 'check_in' | 'help' | 'safe', now: string): UpdateItem {
  const content = {
    check_in: { id: UPDATE_IDS.checkIn, title: 'Safety check-in sent', body: 'We noticed a stop near a reported flood' },
    help: { id: UPDATE_IDS.help, title: 'Help request received', body: 'Simulated workflow · Sample data' },
    safe: { id: UPDATE_IDS.safe, title: 'You marked yourself safe', body: 'Thanks for checking in' },
  }[kind];
  return { ...content, category: 'checkins', icon: 'shield', at: now, target: 'case' };
}

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
export function buildScenario(scenario: Scenario, carry: Carry, now: string): AppState {
  const trip = buildTrip(now);
  const hasWarning = scenario !== 'normal';
  const updates: UpdateItem[] = [contactUpdate(now, carry.contact.name)];
  if (hasWarning) updates.push(warningUpdate(now), routeChangedUpdate(now));

  let selectedRouteId = hasWarning ? carry.selectedRouteId : 'original';
  let alert: TurnAroundAlert | null = null;
  let safetyCase: SafetyCase | null = null;

  if (scenario === 'alternate_route') selectedRouteId = 'alternate';
  if (selectedRouteId === 'alternate') updates.push(routeSelectedUpdate(now));
  if (scenario === 'turn_around') {
    selectedRouteId = 'original';
    alert = makeAlert(now);
    updates.push(turnAroundUpdate(now));
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
  };
}

export function initialState(now: string): AppState {
  return buildScenario(DEFAULT_SCENARIO, DEFAULT_CARRY, now);
}

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
      ? withUpdate(state.updates, routeSelectedUpdate(now))
      : state.updates.filter((u) => u.id !== UPDATE_IDS.routeSelected);
  const readIds = routeId === 'alternate' ? unread(state.readIds, UPDATE_IDS.routeSelected) : state.readIds;
  return { ...state, selectedRouteId: routeId, updates, readIds };
}

function addCaseEvent(c: SafetyCase, event: CaseEvent): SafetyCase {
  return { ...c, events: [...c.events, event] };
}

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'hydrate': {
      const p = action.persisted;
      return buildScenario(
        state.scenario,
        { contact: p.contact, preferences: p.preferences, selectedRouteId: p.selectedRouteId, readIds: p.readIds },
        action.now,
      );
    }
    case 'set_scenario':
      return buildScenario(action.scenario, carryFrom(state), action.now);
    case 'reset':
      return buildScenario(DEFAULT_SCENARIO, DEFAULT_CARRY, action.now);
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
