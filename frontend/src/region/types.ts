/**
 * Hill Country region payloads (docs/api-contract.md, "Hill Country"). Only the fields the console reads.
 * Critical points, areas and drone tours are computed by the backend from the road map, terrain and
 * waterways (backend/population/nodes.py, backend/critical/); nothing here is hardcoded.
 */
export type PointStatus = 'open' | 'unknown' | 'likely_flooded' | 'confirmed_flooded'
export type PointKind = 'crossing' | 'bridge' | 'low_spot'
export type AreaStatus = 'ok' | 'at_risk' | 'partially_cut_off' | 'cut_off'
export type Instruction = 'none' | 'route_out' | 'shelter_in_place' | 'wait_for_check'
export type DangerLevel = 'none' | 'watch' | 'warning' | 'danger' | 'critical'
export type FleetStatus = 'idle' | 'flying' | 'snapshot' | 'returning'

export interface Breakdown { dependency: number; vulnerability: number; p_weight: number; uncertainty: number; urgency: number }

export interface Snapshot {
  point_id: string
  drone_id: string
  time: string
  water_on_road: boolean | null
  est_depth_in: number | null
  people_seen?: number | null
  confidence?: string
}

/** A ranked critical point (top 12 from /api/region/state). */
export interface RankedPoint {
  id: string
  name: string
  kind: PointKind
  waterway: string | null
  lon: number
  lat: number
  p_flooded: number
  status: PointStatus
  priority: number
  breakdown: Breakdown
  node_ids: string[]
  last_snapshot: Snapshot | null
}

/** A road that isn't open, with its geometry (/api/region/flood-layer `segments`; worst status of both directions). */
export interface FloodRoad { id: string; status: PointStatus; name: string; coords: [number, number][] }

/** Every critical point in the region with its status (/api/region/flood-layer). */
export interface MapPoint { id: string; name: string; kind: PointKind; status: PointStatus; lon: number; lat: number }

export interface Area {
  id: string
  name: string
  kind: 'homes' | 'camp' | 'rv_park'
  town: string
  lon: number
  lat: number
  households: number
  status: AreaStatus
  instruction: Instruction
  rescue: 'truck_route' | 'boat_required' | null
  unavoidable_points: string[]
  reasons: string[]
}

export interface FleetDrone {
  id: string
  station: string
  lat: number
  lon: number
  status: FleetStatus
  target: string | null
  eta_s: number
  battery_pct: number
  tour: string[]
  path: [number, number][]
  km_flown: number
}

export interface RegionCounters {
  households_cut_off: number
  nodes_cut_off: number
  points_checked: number
  drone_km: number
  boat_required: number
}

export interface RegionAlert { id: string; event: string; headline: string; active: boolean; emergency?: boolean; area?: string; at?: string }

/** One upstream feed's health (live mode reads USGS, NWS, NOAA MRMS and storm reports). */
export interface FeedSource { status: string; provenance?: string; as_of?: string | null; checked_at?: string | null; detail?: string | null; error?: string | null }

export type RegionMode = 'replay' | 'live'

export interface RegionState {
  mode: RegionMode
  sources: Record<string, FeedSource>
  sim_time: string | null
  scenario_running: boolean
  alerts: RegionAlert[]
  critical_points: RankedPoint[]
  nodes: Area[]
  drones: FleetDrone[]
  counters: Partial<RegionCounters>
}

/** The outreach ladder for one person (texts, polls, calls, family, responders). */
export interface ResponseState {
  episode_level?: DangerLevel | null
  awaiting_reply: boolean
  called: boolean
  call_unanswered: boolean
  family_contacted: boolean
  responders_flagged: boolean
  case_open: boolean
  need_help: boolean
  safe_until: number | null
  timeline: { t: number; what: string }[]
}

export interface Person {
  advice?: string
  response?: ResponseState | null
  user_id: string
  level: DangerLevel
  reasons: string[]
  stopped_in_water: boolean
  location: { lat?: number; lon?: number; state?: string }
  hazard?: { road_name?: string | null; waterway?: string | null }
}

export interface UserInfo { id: string; name: string; age: number | null }

export interface RegionInfo { bbox: { west: number; south: number; east: number; north: number }; stations: { id: string; lon: number; lat: number }[] }

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

/** Light boundary checks: the console must not crash on a payload from an older or newer backend. */
export function parseState(v: unknown): RegionState {
  if (!isObj(v)) throw new Error('Region state is not an object')
  const arr = <T,>(x: unknown) => (Array.isArray(x) ? (x as T[]) : [])
  return {
    mode: v.mode === 'live' ? 'live' : 'replay',
    sources: isObj(v.sources) ? (v.sources as Record<string, FeedSource>) : {},
    sim_time: typeof v.sim_time === 'string' ? v.sim_time : null,
    scenario_running: v.scenario_running === true,
    alerts: arr<RegionAlert>(v.alerts),
    critical_points: arr<RankedPoint>(v.critical_points),
    nodes: arr<Area>(v.nodes),
    drones: arr<FleetDrone>(v.drones).map((d) => ({ ...d, tour: arr<string>(d.tour), path: arr<[number, number]>(d.path) })),
    counters: isObj(v.counters) ? (v.counters as Partial<RegionCounters>) : {},
  }
}
