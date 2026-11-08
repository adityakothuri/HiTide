import { parseState, type FloodRoad, type RegionMode, type MapPoint, type Person, type RegionInfo, type RegionState, type UserInfo } from './types'

/** Replay speed for the July 4 run: 01:00 to 07:30 CDT in about 6.5 minutes. */
export const REPLAY_SPEED = 60

async function getJson(url: string, signal?: AbortSignal): Promise<unknown> {
  const r = await fetch(url, { signal })
  if (!r.ok) throw new Error(`${url.split('?')[0]} returned ${r.status}`)
  return r.json()
}

export async function fetchRegionInfo(signal?: AbortSignal): Promise<RegionInfo> {
  const v = (await getJson('/api/region', signal)) as RegionInfo
  if (!v?.bbox) throw new Error('Region data has no bounds')
  return { bbox: v.bbox, stations: Array.isArray(v.stations) ? v.stations : [] }
}

export async function fetchState(signal?: AbortSignal): Promise<RegionState> {
  return parseState(await getJson('/api/region/state', signal))
}

/** Critical points and non-open roads for the whole region, in one call. */
export async function fetchFloodLayer(info: RegionInfo, signal?: AbortSignal): Promise<{ points: MapPoint[]; roads: FloodRoad[] }> {
  const { west, south, east, north } = info.bbox
  const v = (await getJson(`/api/region/flood-layer?bbox=${west},${south},${east},${north}`, signal)) as { points?: MapPoint[]; segments?: FloodRoad[] }
  return { points: Array.isArray(v.points) ? v.points : [], roads: Array.isArray(v.segments) ? v.segments : [] }
}

export async function fetchPeople(signal?: AbortSignal): Promise<{ total: number; users: Person[] }> {
  const v = (await getJson('/api/users/at-risk?min_level=warning&limit=500', signal)) as { total?: number; users?: Person[] }
  return { total: v.total ?? 0, users: Array.isArray(v.users) ? v.users : [] }
}

export async function fetchUsers(signal?: AbortSignal): Promise<UserInfo[]> {
  const v = (await getJson('/api/users?limit=2000', signal)) as { users?: UserInfo[] }
  return Array.isArray(v.users) ? v.users : []
}

async function post(url: string): Promise<void> {
  const r = await fetch(url, { method: 'POST' })
  if (!r.ok) throw new Error(`${url.split('?')[0]} returned ${r.status}`)
}

export const startReplay = () => post(`/api/demo/start?scenario=hill_country&speed=${REPLAY_SPEED}`)
export const resetReplay = () => post('/api/demo/reset?scenario=hill_country')
/** live: real-time USGS gauges, NWS alerts and NOAA MRMS radar for the same region. */
export const setRegionMode = (mode: RegionMode) => post(`/api/region/mode?mode=${mode}`)
