import { UPDATE_IDS } from '@/data/fixtures';
import { nearestIndex, pointAlong } from '@/domain/routeGeometry';
import type {
  AppState,
  CaseEvent,
  CaseEventKind,
  DangerLevel,
  FloodWarning,
  LngLat,
  SafetyCase,
  Trip,
  TurnAroundAlert,
  UpdateItem,
} from '@/domain/types';
import { caseUpdate, turnAroundUpdate } from '@/state/updates';
import { type Assessment, DANGER_LEVELS, type RoadHit, type TimelineEntry } from './schema';

/**
 * Maps one backend Assessment onto the app state. Pure: the same inputs always give the same state.
 * Truth rules (design/mockups/2026-11-08/consumer-v2): unknown depth is never "dry", no route is called safe,
 * and times the source did not give are left empty rather than filled with a fetch time.
 */

const rank = (level: DangerLevel): number => DANGER_LEVELS.indexOf(level);
const WARNING_RANK = rank('warning');

const FLOODED_STATUSES = new Set(['confirmed_flooded', 'likely_flooded', 'flooded', 'closed']);
const REPLAY_PREFIX = /^REPLAY of ([^:]+):\s*/;

const ADVICE_TEXT: Record<string, string> = {
  turn_around: 'Turn around. Never drive through floodwater.',
  do_not_drive: 'Do not drive right now. Wait for the water to go down.',
  move_to_high_ground: 'Move to higher ground if water is rising near you. Avoid low-water crossings.',
  stay_on_high_ground: 'Stay where you are on high ground until the water goes down.',
  be_ready: 'Be ready to move to higher ground. Avoid low-water crossings.',
};
const DEFAULT_GUIDANCE = 'Avoid low-water crossings. Never drive through floodwater. Turn around, don’t drown.';

const toIso = (epochSeconds: number): string => new Date(epochSeconds * 1000).toISOString();

const isFloodedHit = (h: RoadHit): boolean =>
  FLOODED_STATUSES.has(h.point_status ?? '') || (h.depth_in ?? 0) > 0;

function depthText(depthIn: number | null | undefined): string {
  return depthIn == null || depthIn <= 0 ? 'depth not measured' : `about ${Math.round(depthIn)} in deep`;
}

function statusText(status: string | null | undefined): string {
  if (status === 'confirmed_flooded') return 'confirmed flooded';
  if (status === 'likely_flooded') return 'likely flooded';
  return 'water reported';
}

// ---- warning ------------------------------------------------------------------------------------

function pickHeadline(headlines: readonly string[]): string | null {
  return headlines.find((h) => /emergency/i.test(h)) ?? headlines[0] ?? null;
}

function liveWarning(a: Assessment, homeArea: string): FloodWarning {
  const headline = pickHeadline(a.hazard.alert_headlines);
  const replay = headline ? REPLAY_PREFIX.exec(headline) : null;
  const clean = headline ? headline.replace(REPLAY_PREFIX, '') : null;
  const [event, area] = clean ? clean.split(/ for (.+)/) : [];
  const source = headline
    ? `National Weather Service${replay ? ` · replay of ${replay[1]}` : ''}`
    : 'HiTide assessment';
  return {
    id: 'warning-live',
    event: event?.trim() || 'Flood danger near you',
    area: area?.trim() || homeArea,
    source,
    issuedAt: null,
    expiresAt: null,
    assessedAt: a.assessed_at,
    summary: a.reasons[0] ?? 'HiTide found flood danger near your location.',
    guidance: ADVICE_TEXT[a.advice] ?? DEFAULT_GUIDANCE,
  };
}

// ---- closure and alert --------------------------------------------------------------------------

interface FloodedRoad {
  /** Stable identity (backend edge or point id), so one flooded crossing is one alert. */
  key: string;
  road: string;
  at: LngLat;
  source: string;
}

function floodedRoad(state: AppState, a: Assessment, position: LngLat | null): FloodedRoad | null {
  const route = state.trip.routes.original.coords;
  const ahead = a.hazard.ahead.find(isFloodedHit);
  if (ahead) {
    const from = position ? nearestIndex(route, position) : 0;
    return {
      key: ahead.edge_id,
      road: ahead.road_name ?? 'the road ahead',
      at: pointAlong(route, from, ahead.distance_m ?? 0),
      source: `HiTide · ${statusText(ahead.point_status)}, ${depthText(ahead.depth_in)}`,
    };
  }
  // `route` hits describe whichever route was last sent for checking; draw them only when that's the usual route.
  const onRoute = state.selectedRouteId === 'original' ? a.hazard.route.find(isFloodedHit) : undefined;
  if (onRoute) {
    return {
      key: onRoute.edge_id,
      road: onRoute.road_name ?? 'your route',
      at: pointAlong(route, 0, onRoute.distance_m ?? 0),
      source: `HiTide route check · ${statusText(onRoute.point_status)}, ${depthText(onRoute.depth_in)}`,
    };
  }
  const worst = a.hazard.worst_point;
  if (worst?.on_my_road && FLOODED_STATUSES.has(worst.status ?? '') && position) {
    return {
      key: worst.id,
      road: worst.name ?? a.hazard.road_name ?? 'your road',
      at: position,
      source: `HiTide · ${statusText(worst.status)}, ${depthText(a.hazard.depth_in)}`,
    };
  }
  return null;
}

function nextTrip(state: AppState, flooded: FloodedRoad | null, active: boolean, at: string): Trip {
  const prev = state.trip.closure;
  const closure = flooded
    ? prev?.road === flooded.road
      ? prev
      : { road: flooded.road, at: flooded.at, source: flooded.source, reportedAt: at }
    : active
      ? prev // keep the last reported closure while the danger lasts; the lookahead moves on
      : null;
  if (closure === prev && state.trip.routes.original.affectedRoad === (closure?.road ?? null)) return state.trip;
  return {
    ...state.trip,
    closure,
    routes: {
      ...state.trip.routes,
      original: { ...state.trip.routes.original, affectedRoad: closure?.road ?? null },
    },
  };
}

function nextAlert(state: AppState, a: Assessment, flooded: FloodedRoad | null): TurnAroundAlert | null {
  const prev = state.alert;
  const turn =
    a.advice === 'turn_around' && a.location?.state === 'driving' && !a.location_stale && rank(a.level) >= WARNING_RANK;
  // An acknowledged alert is remembered through a brief dip in level, so the same road is never re-spoken, and is
  // cleared once the danger is fully over, so a later episode on the same road alerts again.
  if (!turn) return prev?.acknowledged && a.level !== 'none' ? prev : null;
  // Same advice but the look-ahead lost its hit: keep the alert already raised rather than inventing a new one.
  if (!flooded && prev) return prev;
  const road = flooded?.road ?? a.hazard.road_name ?? 'the road ahead';
  const id = `alert-${flooded?.key ?? road}`;
  if (prev && (prev.id === id || prev.road === road)) return prev;
  return {
    id,
    road,
    message: 'Flooded road ahead. Turn around.',
    spokenText: `Flooded road ahead on ${road}. Turn around. Do not drive through floodwater.`,
    issuedAt: a.assessed_at,
    acknowledged: false,
  };
}

// ---- safety case --------------------------------------------------------------------------------

const STOP = /^(critical|danger)( reminder)? -> .*(poll|voice|open_case)|^no reply to poll/;
const HELP = /^HELP from /;
const FAMILY = /^family contacted/;
const RESPONDERS = /responders flagged/;
const SAFE = /^SAFE from [\w ]+$/;
const ALL_CLEAR = /^all clear$/;
const ASSISTANT = /^assistant (call|line)\b/;
const ASSISTANT_SUMMARY = /^assistant call: (.+)$/;

/** The latest assistant-line entry as one case step: requested, then the call's summary once it ends. */
function assistantEvent(entry: TimelineEntry | undefined): CaseEvent | null {
  if (!entry) return null;
  const summary = ASSISTANT_SUMMARY.exec(entry.what)?.[1];
  const simulated = entry.what.includes('(simulated)');
  const detail = summary
    ? summary
    : simulated
      ? 'Simulated call'
      : /unavailable/.test(entry.what)
        ? 'Assistant line unavailable'
        : /not detected/.test(entry.what)
          ? 'No call detected'
          : 'Calling the HiTide assistant';
  return { kind: 'assistant_call', at: toIso(entry.t), simulated, detail };
}

/** Entries since the last all clear: older entries belong to an earlier episode. */
function currentEpisode(timeline: readonly TimelineEntry[]): readonly TimelineEntry[] {
  let start = 0;
  timeline.forEach((e, i) => {
    if (ALL_CLEAR.test(e.what)) start = i + 1;
  });
  return timeline.slice(start);
}

function eventsFrom(a: Assessment, simulatedOutreach: boolean): CaseEvent[] {
  const r = a.response;
  if (!r) return [];
  const episode = currentEpisode(r.timeline);
  const first = (re: RegExp) => episode.find((e) => re.test(e.what));
  const events: CaseEvent[] = [];
  const push = (kind: CaseEventKind, entry: TimelineEntry | undefined, simulated: boolean) => {
    if (entry) events.push({ kind, at: toIso(entry.t), simulated });
  };
  push('stop_detected', first(STOP), false);
  push('help_received', first(HELP), false);
  if (r.family_contacted) push('contact_notified', first(FAMILY), simulatedOutreach);
  if (r.responders_flagged) push('responders_flagged', first(RESPONDERS) ?? first(FAMILY), simulatedOutreach);
  push('marked_safe', first(SAFE), false);
  const assistant = assistantEvent([...episode].reverse().find((e) => ASSISTANT.test(e.what)));
  if (assistant) events.push(assistant);
  return events;
}

type RemoteStatus = SafetyCase['status'] | null;

function remoteStatus(a: Assessment, events: readonly CaseEvent[]): RemoteStatus {
  const r = a.response;
  if (!r) return null;
  if (r.need_help) return 'help_requested';
  // A SAFE reply from any channel (app, SMS, call) resolves the episode; the person sees the resolved screen.
  if (events.some((e) => e.kind === 'marked_safe')) return 'safe';
  // The check-in is for a stopped car. While driving, the turn-around alert speaks instead (no tapping at speed).
  if (a.location?.state === 'driving') return null;
  if (r.awaiting_reply || r.case_open) return 'checking';
  return null;
}

function nextCase(state: AppState, a: Assessment, position: LngLat | null): SafetyCase | null {
  const prev = state.safetyCase;
  const events = eventsFrom(a, state.connection.mode !== 'live');
  const remote = remoteStatus(a, events);

  // Never undo what the person did on this phone while the backend catches up, and never auto-close help.
  if (prev?.status === 'help_requested' && remote !== 'help_requested') return prev;
  if (prev?.status === 'safe' && remote !== 'help_requested') return prev;
  if (remote === null) return null;
  // A case that is already resolved is not re-opened after the person dismissed it.
  if (!prev && remote === 'safe') return null;

  const openedAt = events.find((e) => e.kind === 'stop_detected')?.at ?? a.assessed_at;
  const withStop: CaseEvent[] = events.some((e) => e.kind === 'stop_detected')
    ? events
    : [{ kind: 'stop_detected', at: openedAt, simulated: false }, ...events];
  return {
    id: prev?.id ?? `case-${openedAt}`,
    status: remote,
    locationLabel: a.hazard.road_name ?? a.hazard.worst_point?.name ?? 'Your location',
    location: position ?? prev?.location ?? state.trip.origin,
    openedAt: prev?.openedAt ?? openedAt,
    // A tap on "Call the assistant" shows at once; the backend's own entry replaces it when it arrives.
    events: withStop.some((e) => e.kind === 'assistant_call')
      ? withStop
      : [...withStop, ...(prev?.events.filter((e) => e.kind === 'assistant_call') ?? [])],
    minimized: prev?.status === remote ? prev.minimized : false,
  };
}

// ---- outreach ------------------------------------------------------------------------------------

/** A ladder entry that reached the person: `critical -> voice:critical_call, open_case:case`, `warning -> text:warning`. */
const OUTREACH = / -> /;
const VOICE_CALL = / -> (.*\bvoice:|call$)/;

interface Outreach {
  callPlaced: boolean;
  lastOutreach: string | null;
}

/** What HiTide did to reach the person in the current episode: was a call placed, and the latest outreach entry. */
export function outreachFrom(a: Assessment): Outreach {
  const episode = a.response ? currentEpisode(a.response.timeline) : [];
  const latest = [...episode].reverse().find((e) => OUTREACH.test(e.what));
  return { callPlaced: episode.some((e) => VOICE_CALL.test(e.what)), lastOutreach: latest?.what ?? null };
}

// ---- updates feed -------------------------------------------------------------------------------

interface Feed {
  updates: UpdateItem[];
  readIds: readonly string[];
}

/** Keeps an unchanged item as is (its time and read state); a changed item is replaced and marked unread. */
function upsert(feed: Feed, item: UpdateItem): Feed {
  const prev = feed.updates.find((u) => u.id === item.id);
  if (prev && prev.title === item.title && prev.body === item.body) return feed;
  return {
    updates: [...feed.updates.filter((u) => u.id !== item.id), item],
    readIds: feed.readIds.filter((id) => id !== item.id),
  };
}

const LIVE_IDS = new Set<string>([UPDATE_IDS.warning, UPDATE_IDS.routeChanged, UPDATE_IDS.turnAround]);

function nextFeed(state: AppState, next: Pick<AppState, 'warning' | 'trip' | 'alert' | 'safetyCase'>, at: string): Feed {
  const wanted = new Set<string>();
  let feed: Feed = { updates: [...state.updates], readIds: state.readIds };
  const add = (item: UpdateItem) => {
    wanted.add(item.id);
    feed = upsert(feed, item);
  };

  if (next.warning) {
    add({
      id: UPDATE_IDS.warning,
      category: 'general',
      icon: 'warning',
      title: next.warning.event,
      body: `${next.warning.area} · ${next.warning.source}`,
      at,
      target: 'warning',
      actionLabel: 'View warning',
    });
  }
  if (next.trip.closure) {
    add({
      id: UPDATE_IDS.routeChanged,
      category: 'trips',
      icon: 'car',
      title: 'Your work route has changed',
      body: `Flooding reported on ${next.trip.closure.road}`,
      at: next.trip.closure.reportedAt,
      target: 'route',
      actionLabel: 'Review route',
    });
  }
  if (next.alert) add(turnAroundUpdate(next.alert.issuedAt, next.alert.road));

  const c = next.safetyCase;
  if (c) {
    add(caseUpdate('check_in', c.openedAt));
    const help = c.events.find((e) => e.kind === 'help_received');
    const notified = c.events.some((e) => e.kind === 'contact_notified');
    if (help) add(caseUpdate('help', help.at, notified ? 'Your emergency contact was notified' : 'HiTide is checking on you'));
    const safe = c.events.find((e) => e.kind === 'marked_safe');
    if (safe) add(caseUpdate('safe', safe.at));
  }

  // Live-derived items that no longer apply go away; user-driven items (contact, case) stay.
  // A route choice only means something while a closure exists.
  const updates = feed.updates.filter(
    (u) => (!LIVE_IDS.has(u.id) || wanted.has(u.id)) && (u.id !== UPDATE_IDS.routeSelected || next.trip.closure !== null),
  );
  return { updates, readIds: feed.readIds };
}

// ---- entry point --------------------------------------------------------------------------------

export function applyAssessment(state: AppState, a: Assessment): AppState {
  const at = a.assessed_at;
  const position: LngLat | null = a.location ? [a.location.lon, a.location.lat] : state.position;
  const active = rank(a.level) >= WARNING_RANK;

  const flooded = active ? floodedRoad(state, a, position) : null;
  const trip = nextTrip(state, flooded, active, at);
  const warning = active ? liveWarning(a, state.user.homeArea) : null;
  const alert = nextAlert(state, a, flooded);
  const safetyCase = nextCase(state, a, position);
  const feed = nextFeed(state, { warning, trip, alert, safetyCase }, at);

  return {
    ...state,
    position,
    warning,
    trip,
    selectedRouteId: trip.closure ? state.selectedRouteId : 'original',
    alert,
    safetyCase,
    updates: feed.updates,
    readIds: feed.readIds,
    connection: {
      ...state.connection,
      status: 'live',
      assessedAt: at,
      level: a.level,
      degraded: a.hazard.degraded_sources.length > 0 || a.confidence === 'low',
      topReason: a.reasons[0] ?? null,
      ...outreachFrom(a),
    },
  };
}
