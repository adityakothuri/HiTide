/**
 * Domain types for the Flood Watch consumer app.
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
  issuedAt: string;
  expiresAt: string;
  summary: string;
  guidance: string;
}

export interface GaugeReading {
  id: string;
  name: string;
  stageFt: number;
  /** Stage at which the river begins to flood nearby low crossings. */
  actionStageFt: number;
  trend: 'rising' | 'steady' | 'falling';
  /** Hourly stage, oldest first. */
  series: readonly number[];
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
export type CaseEventKind = 'stop_detected' | 'help_received' | 'contact_notified' | 'marked_safe';

export interface CaseEvent {
  kind: CaseEventKind;
  at: string;
  /** True when this step is simulated by the demo (no real call, text, or dispatch). */
  simulated: boolean;
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
