// Mirror of backend/api/schemas.py (docs/api-contract.md). Keep in sync by hand.
// Fields marked "proposed" are listed under "Proposed additions (frontend)" in the contract.
// They are optional, and the UI falls back when they are missing.

export type RoadStatus = 'open' | 'caution' | 'closed' | 'float' | 'boat'
export type Situation = 'parked' | 'planning' | 'driving' | 'stopped_in_water'
export type CaseState =
  | 'monitoring'
  | 'calling'
  | 'contacting_family'
  | 'drone_en_route'
  | 'verified'
  | 'handed_to_responders'
  | 'resolved'

export interface LatLon {
  lat: number
  lon: number
}

export interface SegmentState {
  edge_id: string
  depth_in: number
  status: RoadStatus
}

export interface SegmentsUpdate {
  t_sim_s: number
  river_wse_m: number
  segments: SegmentState[]
}

export interface DriverPublic {
  id: string
  name: string
  lat: number
  lon: number
  heading_deg: number
  situation: Situation
  is_demo: boolean
  urgency: number
}

export interface Alert {
  id: string
  event: string
  headline: string
  active: boolean
  simulated: boolean
  polygon: GeoJSON.Geometry | null
}

export interface OutreachEvent {
  id: string
  ts: string
  driver_id: string
  recipient: 'driver' | 'parent' | 'emergency_contact'
  channel: 'text' | 'poll' | 'voice' | 'tts_in_app'
  body: string
  mode: 'mock' | 'photon'
  status: 'queued' | 'sent' | 'delivered' | 'read' | 'failed' | 'blocked'
  case_id: string | null
  provider?: 'stable' | 'photon2' // live sends only
  call_id?: string // placed voice calls only (ElevenLabs conversation id)
}

export interface TurnAround {
  driver_id: string
  message: string
  hazard_edge_id: string
  hazard_depth_in: number
  distance_m: number
}

export interface Reroute {
  driver_id: string
  reason: string
  route: GeoJSON.LineString
  blocked_edge_ids: string[]
  distance_m: number
}

export interface TimelineEntry {
  ts: string
  t_case_s: number
  kind: string
  text: string
  simulated?: boolean // proposed
}

export interface VisionPerson {
  placement: 'on_roof' | 'in_water' | 'on_shore' | 'inside_unknown'
  box: [number, number, number, number]
  conf: number
}

export interface VisionResult {
  image_url: string
  annotated_url: string
  car_detected: boolean
  water_level: 'none' | 'wheels' | 'doors' | 'windows' | 'roof'
  water_level_source: 'manual_label' | 'rule'
  people: VisionPerson[]
  night_mode: boolean
  thermal_simulated: boolean
  recommendation: 'truck_route_available' | 'boat_required'
}

export interface ResponderView {
  location: LatLon
  people_count: number | null
  water_depth_in: number
}

export interface Case {
  id: string
  driver_id: string
  driver_name: string
  state: CaseState
  urgency: number
  urgency_reasons: string[]
  responder_flag: boolean
  location: LatLon
  depth_in: number
  opened_at: string
  timeline: TimelineEntry[]
  vision: VisionResult | null
  responder_view: ResponderView
  vehicle?: string // proposed
  emergency_contact_name?: string // proposed
}

export interface DroneState {
  id: string
  case_id: string
  lat: number
  lon: number
  eta_s: number
  status: 'launching' | 'en_route' | 'on_scene' | 'returning'
  crew_eta_s?: number // proposed
}

export interface Counters {
  drivers_warned: number
  drivers_rerouted: number
  cars_stopped_in_water: number
  people_verified: number
  est_claims_avoided_usd: number
}

export interface DemoStep {
  step: number
  title: string
  detail: string
}

export interface StateSnapshot {
  t_sim_s: number
  river_wse_m: number
  alert: Alert | null
  segments: SegmentState[]
  drivers: DriverPublic[]
  cases: Case[]
  drones: DroneState[]
  counters: Counters
  drivers_opted_in?: number
}

export type EventMap = {
  snapshot: StateSnapshot
  'segments.update': SegmentsUpdate
  'drivers.update': { drivers: DriverPublic[] }
  alert: Alert
  outreach: OutreachEvent
  turn_around: TurnAround
  reroute: Reroute
  'case.update': Case
  'drone.update': DroneState
  counters: Counters
  'demo.step': DemoStep
}

export type EventType = keyof EventMap

export type WsEvent = {
  [K in EventType]: { type: K; seq: number; ts: string; payload: EventMap[K] }
}[EventType]

export interface FeedStatus {
  name: string
  source: 'live' | 'cached' | 'unavailable'
  fetched_at: string | null
}

export interface Feeds {
  nws_alerts?: FeedStatus
  usgs_gage?: FeedStatus & { latest?: { time: string; value_ft: number } }
  usgs_flood_impacts?: FeedStatus
}

export interface Town {
  segments: GeoJSON.FeatureCollection<GeoJSON.LineString, SegmentProps>
  river: GeoJSON.Feature | GeoJSON.FeatureCollection
  bounds: [number, number, number, number]
  center: [number, number]
}

export interface SegmentProps {
  edge_id: string
  name: string | null
  length_m: number
  elev_m: number
  highway?: string
}

/** Drones only map and report cars in the water to emergency services; recall is the one command. */
export type DroneCommand = 'return'
export type Reply = 'safe' | 'need_help'
