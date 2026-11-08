/**
 * Domain types for the HiTide consumer app.
 * These are the only shapes screens see. A future backend adapter maps its records to these.
 */

export type LngLat = readonly [number, number];

export interface UserProfile {
  id: string;
  firstName: string;
  fullName: string;
  initials: string;
  homeArea: string;
}

export interface EmergencyContact {
  name: string;
  relationship: string;
  phone: string;
}

export interface Preferences {
  spokenAlerts: boolean;
  locationSharing: boolean;
}

export type RouteId = 'original' | 'alternate';

export interface RouteOption {
  id: RouteId;
  label: string;
  via: string;
  distanceMi: number;
  durationMin: number;
  coords: readonly LngLat[];
  /** Road on this route with a reported closure, if any. */
  affectedRoad: string | null;
}

export interface Trip {
  id: string;
  name: string;
  from: string;
  to: string;
  origin: LngLat;
  destination: LngLat;
  routes: Record<RouteId, RouteOption>;
  closure: { road: string; at: LngLat; source: string; reportedAt: string } | null;
}

export interface FloodWarning {
  id: string;
  event: string;
  area: string;
  source: string;
  /** Null when the source did not provide it. Never filled in with a fetch time. */
  issuedAt: string | null;
  expiresAt: string | null;
  /** When HiTide last assessed this warning against your location, if it did. */
  assessedAt: string | null;
  summary: string;
  guidance: string;
}

export interface GaugeReading {
  id: string;
  name: string;
  stageFt: number;
  /** Stage at which the river begins to flood nearby low crossings. Null when the source doesn't publish one. */
  actionStageFt: number | null;
  /** NWS flood category at this stage ('minor', 'moderate', 'major'), when the source reports one. */
  floodCategory: string | null;
  trend: 'rising' | 'steady' | 'falling';
  /** Stage samples, oldest first, `seriesStepMinutes` apart. */
  series: readonly number[];
  seriesStepMinutes: number;
  observedAt: string;
  source: string;
}

export type UpdateCategory = 'trips' | 'checkins' | 'general';
export type UpdateTarget = 'warning' | 'route' | 'contact' | 'case';

export interface UpdateItem {
  id: string;
  category: UpdateCategory;
  icon: 'warning' | 'car' | 'person' | 'shield' | 'route';
  title: string;
  body: string;
  at: string;
  target: UpdateTarget;
  actionLabel?: string;
}

export interface TurnAroundAlert {
  id: string;
  road: string;
  message: string;
  spokenText: string;
  issuedAt: string;
  acknowledged: boolean;
}

export type CaseStatus = 'checking' | 'help_requested' | 'safe';
export type CaseEventKind =
  | 'stop_detected'
  | 'help_received'
  | 'assistant_call'
  | 'contact_notified'
  | 'responders_flagged'
  | 'marked_safe';

export interface CaseEvent {
  kind: CaseEventKind;
  at: string;
  /** True when this step is simulated by the demo (no real call, text, or dispatch). */
  simulated: boolean;
  /** Extra text for the step, e.g. the assistant call's summary. */
  detail?: string;
}

export interface SafetyCase {
  id: string;
  status: CaseStatus;
  locationLabel: string;
  location: LngLat;
  openedAt: string;
  events: readonly CaseEvent[];
  /** The user left the status screen; the case stays active. */
  minimized: boolean;
}

export type Scenario =
  | 'normal'
  | 'flood_warning'
  | 'alternate_route'
  | 'turn_around'
  | 'check_in'
  | 'help_requested'
  | 'resolved';

/** Road / crossing state, as the ops dashboard shows it. Unknown is never open. */
export type FloodStatus = 'confirmed_flooded' | 'likely_flooded' | 'unknown' | 'open';

export interface FloodRoad {
  id: string;
  name: string;
  status: FloodStatus;
  coords: readonly LngLat[];
}

export interface FloodPoint {
  id: string;
  name: string;
  kind: string;
  status: FloodStatus;
  at: LngLat;
}

export interface FloodGaugePoint {
  site: string;
  name: string;
  at: LngLat;
  stageFt: number | null;
  /** NWS category ('major', 'moderate', 'minor', 'action') or null when below flood stages / unknown. */
  category: string | null;
}

/** The flood picture for the map window: the same layers the dashboard draws, limited to this area. */
export interface FloodLayer {
  /** Observation time (the replay clock in replay mode). */
  at: string | null;
  roads: readonly FloodRoad[];
  points: readonly FloodPoint[];
  gauges: readonly FloodGaugePoint[];
  alerts: readonly string[];
  /** True for the illustrative sample picture (no backend). */
  sample: boolean;
  /** True when the backend is replaying July 4, 2025 rather than live Texas feeds. */
  replay: boolean;
}

/** A way to higher ground from the person's position. Never described as safe. */
export interface Directions {
  text: string;
  kind: 'route' | 'stay' | 'none';
  roadNames: readonly string[];
  lengthM: number;
  lines: readonly (readonly LngLat[])[];
  avoid: readonly string[];
}

/** One way to make the trip, with the flooding reported on it. Never described as safe. */
export interface RouteChoice {
  id: string;
  label: string;
  via: readonly string[];
  lengthM: number;
  minutes: number;
  /** flooded: crosses reported flooding · likely: likely flooding · clear: no flooding reported. */
  status: 'flooded' | 'likely' | 'clear';
  flooded: readonly string[];
  likely: readonly string[];
  lines: readonly (readonly LngLat[])[];
}

/** The assistant line: what the app knows after asking the backend to prepare a call. */
export interface AssistantLine {
  mode: 'live' | 'mock' | 'unavailable';
  /** The assistant's number to dial (live mode only). Never persisted. */
  phone: string | null;
  requestedAt: string;
}

/** Backend danger level for this user (docs/api-contract.md, Per-user danger). */
export type DangerLevel = 'none' | 'watch' | 'warning' | 'danger' | 'critical';

export type ConnectionStatus = 'connecting' | 'live' | 'offline';
export type DriveStatus = 'idle' | 'preparing' | 'driving' | 'stopped';

/** Where the app's flood picture comes from. Never persisted. */
export interface Connection {
  /** 'mock': local sample data. 'live': the HiTide backend. */
  kind: 'mock' | 'live';
  status: ConnectionStatus;
  /** Backend mode: 'replay' (July 4, 2025) or 'live' (real-time Texas feeds). */
  mode: 'replay' | 'live' | null;
  /** Time of the latest backend assessment (the replay clock in replay mode). */
  assessedAt: string | null;
  level: DangerLevel | null;
  /** Development demo drive that sends location pings along the trip. */
  drive: DriveStatus;
  /** Remote updates are paused while a developer scenario is shown. */
  paused: boolean;
  /** Development: writes fail on purpose to exercise error states. */
  failWrites: boolean;
  /** Some evidence was missing or low-confidence in the last assessment: "nothing found" must not read as clear. */
  degraded: boolean;
  /** The backend's top reason for the current level (e.g. why a watch is in effect). */
  topReason: string | null;
  /** The backend placed a voice call to this person in the current episode (timeline `-> voice:` or `-> call`). */
  callPlaced: boolean;
  /** The latest outreach entry in the backend timeline (e.g. `warning -> text:warning`), or null. */
  lastOutreach: string | null;
}

/** A location the person set by dropping a pin, and the level the backend gave it. */
export interface LastPin {
  at: LngLat;
  level: DangerLevel | null;
  requestedAt: string;
}

export interface AppState {
  scenario: Scenario;
  user: UserProfile;
  contact: EmergencyContact;
  preferences: Preferences;
  trip: Trip;
  selectedRouteId: RouteId;
  warning: FloodWarning | null;
  gauge: GaugeReading;
  updates: readonly UpdateItem[];
  readIds: readonly string[];
  alert: TurnAroundAlert | null;
  safetyCase: SafetyCase | null;
  /** Last position the backend assessed (live mode). Null in sample-data mode. */
  position: LngLat | null;
  floodLayer: FloodLayer | null;
  directions: Directions | null;
  /** Ways to make the trip (backend in live mode, a sample pair otherwise), and which one the person chose. */
  routeChoices: readonly RouteChoice[];
  selectedChoiceId: string | null;
  assistant: AssistantLine | null;
  /** The last location set on the map (Set location), so the result screen knows what happened. */
  lastPin: LastPin | null;
  connection: Connection;
}

/** What the app must show right now. Urgent modes hide ordinary tabs. */
export type FlowMode = 'normal' | 'turn_around' | 'check_in' | 'support' | 'resolved';

/** Subset of state that survives restarts. Urgent overlays are never persisted. */
export interface PersistedState {
  version: 1;
  contact: EmergencyContact;
  preferences: Preferences;
  selectedRouteId: RouteId;
  readIds: readonly string[];
}
