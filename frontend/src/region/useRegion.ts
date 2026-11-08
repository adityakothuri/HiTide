import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchFloodLayer, fetchPeople, fetchRegionInfo, fetchState, fetchUsers, resetReplay, setRegionMode, startReplay } from './api'
import type { FloodRoad, MapPoint, Person, RegionInfo, RegionMode, RegionState } from './types'

const STATE_MS = 1_000
const SLOW_MS = 3_000
const TRAIL_CAP = 400
const HISTORY_CAP = 600

/** One sample of the situation at a sim time, for sparklines and the timeline chart. */
export interface HistoryPoint { t: number; critical: number; danger: number; warning: number; homesCutOff: number; checked: number }

export interface RegionData {
  status: 'loading' | 'ready' | 'error'
  error: string | null
  info: RegionInfo | null
  state: RegionState | null
  points: MapPoint[]
  /** Roads that aren't open: confirmed flooded, likely flooded, or not yet checked. */
  roads: FloodRoad[]
  people: Person[]
  peopleTotal: number
  names: Record<string, string>
  pointNames: Record<string, string>
  /** Flown path per drone, built from successive positions. */
  trails: Record<string, [number, number][]>
  /** Situation over sim time, oldest first. Restarts with each run. */
  history: HistoryPoint[]
  start: () => Promise<void>
  reset: () => Promise<void>
  setMode: (mode: RegionMode) => Promise<void>
}

/** Repeats `fn` every `ms` while the tab is visible. */
function usePoll(fn: () => Promise<void>, ms: number, enabled: boolean) {
  const ref = useRef(fn)
  useEffect(() => {
    ref.current = fn
  }, [fn])
  useEffect(() => {
    if (!enabled) return
    let alive = true
    let timer = 0
    const tick = async () => {
      if (!document.hidden) await ref.current().catch(() => undefined)
      if (alive) timer = window.setTimeout(tick, ms)
    }
    void tick()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [ms, enabled])
}

/** Hill Country region: people at risk, areas, critical points and the drone fleet, polled from the backend. */
export function useRegion(enabled: boolean): RegionData {
  const [info, setInfo] = useState<RegionInfo | null>(null)
  const [state, setState] = useState<RegionState | null>(null)
  const [points, setPoints] = useState<MapPoint[]>([])
  const [roads, setRoads] = useState<FloodRoad[]>([])
  const [people, setPeople] = useState<{ total: number; users: Person[] }>({ total: 0, users: [] })
  const [names, setNames] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [trails, setTrails] = useState<Record<string, [number, number][]>>({})
  const lastSim = useRef<string | null>(null)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const latest = useRef<RegionState | null>(null)

  useEffect(() => {
    if (!enabled) return
    const ac = new AbortController()
    fetchRegionInfo(ac.signal).then(setInfo, (e: Error) => !ac.signal.aborted && setError(e.message))
    fetchUsers(ac.signal).then((us) => setNames(Object.fromEntries(us.map((u) => [u.id, u.name]))), () => undefined)
    return () => ac.abort()
  }, [enabled])

  const pollState = useCallback(async () => {
    try {
      const s = await fetchState()
      setError(null)
      setState(s)
      latest.current = s
      // A new run (time went backwards) starts fresh trails.
      const restarted = lastSim.current != null && s.sim_time != null && s.sim_time < lastSim.current
      lastSim.current = s.sim_time
      if (restarted) setHistory([])
      setTrails((prev) => {
        const next: Record<string, [number, number][]> = restarted ? {} : { ...prev }
        for (const d of s.drones) {
          const t = next[d.id] ?? []
          const last = t[t.length - 1]
          if (d.status === 'idle') next[d.id] = []
          else if (!last || last[0] !== d.lon || last[1] !== d.lat) next[d.id] = [...t, [d.lon, d.lat] as [number, number]].slice(-TRAIL_CAP)
        }
        return next
      })
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])
  const pollSlow = useCallback(async () => {
    const [pp] = await Promise.all([fetchPeople(), info ? fetchFloodLayer(info).then((f) => { setPoints(f.points); setRoads(f.roads) }) : Promise.resolve()])
    setPeople(pp)
    const s = latest.current
    const t = s?.sim_time ? Date.parse(s.sim_time) : NaN
    if (!s?.scenario_running || s.mode !== 'replay' || !Number.isFinite(t)) return
    const count = (lv: Person['level']) => pp.users.filter((u) => u.level === lv).length
    const sample: HistoryPoint = {
      t,
      critical: count('critical'),
      danger: count('danger'),
      warning: count('warning'),
      homesCutOff: s.counters.households_cut_off ?? 0,
      checked: s.counters.points_checked ?? 0,
    }
    setHistory((h) => (h.length && h[h.length - 1].t >= t ? h : [...h, sample].slice(-HISTORY_CAP)))
  }, [info])
  usePoll(pollState, STATE_MS, enabled)
  usePoll(pollSlow, SLOW_MS, enabled)

  const pointNames = useMemo(() => {
    const out: Record<string, string> = {}
    for (const p of points) out[p.id] = p.name
    for (const p of state?.critical_points ?? []) out[p.id] = p.name
    return out
  }, [points, state?.critical_points])

  const start = useCallback(async () => {
    lastSim.current = null
    setTrails({})
    setHistory([])
    await startReplay()
    await pollState()
  }, [pollState])
  const reset = useCallback(async () => {
    await resetReplay()
    setTrails({})
    setHistory([])
    await Promise.all([pollState(), pollSlow().catch(() => undefined)])
  }, [pollState, pollSlow])

  const setMode = useCallback(async (mode: RegionMode) => {
    await setRegionMode(mode)
    lastSim.current = null
    setTrails({})
    setHistory([])
    await Promise.all([pollState(), pollSlow().catch(() => undefined)])
  }, [pollState, pollSlow])

  return {
    setMode,
    status: error && !state ? 'error' : state ? 'ready' : 'loading',
    error,
    info,
    state,
    points,
    roads,
    people: people.users,
    peopleTotal: people.total,
    names,
    pointNames,
    trails,
    history,
    start,
    reset,
  }
}
