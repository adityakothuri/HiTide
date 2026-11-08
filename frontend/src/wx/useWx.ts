import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { dataMode } from '../config/dataMode'
import { loadLiveSource } from './liveSource'
import { loadReplaySource } from './replaySource'
import type { RainProduct, WxMode, WxSnapshot, WxSource } from './types'

/** One step per tick while playing: 6.5 h of replay in about 20 s. */
const PLAY_TICK_MS = 250

/** One base field at a time (risk, rain or depth) plus overlays. */
export type BaseField = 'risk' | 'rain' | 'depth' | 'none'
export interface WxLayers { base: BaseField; rainProduct: RainProduct; opacity: number; gauges: boolean; roads: boolean }

export const DEFAULT_OPACITY = 0.7

export type WxLoad = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; source: WxSource }

export interface WxState {
  load: WxLoad
  t: number
  setT: (t: number) => void
  playing: boolean
  setPlaying: (p: boolean) => void
  step: (dir: 1 | -1) => void
  snapshot: WxSnapshot | null
  layers: WxLayers
  setLayers: (fn: (l: WxLayers) => WxLayers) => void
}

/** VITE_WX_MODE overrides; otherwise follow the test/real data mode. */
async function wxMode(): Promise<WxMode> {
  const forced = import.meta.env.VITE_WX_MODE
  if (forced === 'live' || forced === 'replay') return forced
  return (await dataMode()) === 'real' ? 'live' : 'replay'
}

/** Real mode with the live feeds down still shows a map: the replay, labelled as such. */
async function loadSource(): Promise<WxSource> {
  if ((await wxMode()) === 'replay') return loadReplaySource()
  try {
    return await loadLiveSource()
  } catch (e) {
    console.warn('Live weather unavailable, falling back to the replay', e)
    const replay = await loadReplaySource()
    return { ...replay, note: `Live weather unavailable · showing ${replay.note.toLowerCase()}` }
  }
}

/** Optional `?t=2025-07-04T09:30:00Z` starts the replay at that time (used for screenshots). */
function initialT({ range, mode }: WxSource): number {
  const q = new URLSearchParams(window.location.search).get('t')
  const ms = q ? Date.parse(q) : NaN
  if (Number.isFinite(ms)) return Math.min(range[1], Math.max(range[0], ms))
  return mode === 'live' ? range[1] : range[0] // live opens on "now", the replay at its start
}

/** `initial` overrides the default layers (the monitor starts with a faded surface and no overlays). */
export function useWx(initialBase: BaseField = 'risk', initial: Partial<WxLayers> = {}): WxState {
  const [load, setLoad] = useState<WxLoad>({ status: 'loading' })
  const [t, setTRaw] = useState(0)
  const [playing, setPlaying] = useState(false)
  const tRef = useRef(t)
  useEffect(() => {
    tRef.current = t
  }, [t])
  const [layers, setLayersRaw] = useState<WxLayers>(() => ({ base: initialBase, rainProduct: 'p1h', opacity: DEFAULT_OPACITY, gauges: true, roads: true, ...initial }))

  useEffect(() => {
    let alive = true
    loadSource().then(
      (source) => {
        if (!alive) return
        setLoad({ status: 'ready', source })
        setTRaw(initialT(source))
      },
      (e: unknown) => alive && setLoad({ status: 'error', message: e instanceof Error ? e.message : String(e) }),
    )
    return () => {
      alive = false
    }
  }, [])

  const source = load.status === 'ready' ? load.source : null

  const setT = useCallback(
    (next: number) => {
      if (!source) return
      const [a, b] = source.range
      setTRaw(Math.min(b, Math.max(a, Math.round((next - a) / source.stepMs) * source.stepMs + a)))
    },
    [source],
  )

  const step = useCallback((dir: 1 | -1) => source && setT(t + dir * source.stepMs), [source, setT, t])

  useEffect(() => {
    if (!playing || !source) return
    const id = window.setInterval(() => {
      const next = Math.min(source.range[1], tRef.current + source.stepMs)
      setTRaw(next)
      if (next >= source.range[1]) setPlaying(false) // stop at the end of the window
    }, PLAY_TICK_MS)
    return () => window.clearInterval(id)
  }, [playing, source])

  const snapshot = useMemo(() => (source ? source.at(t) : null), [source, t])
  const setLayers = useCallback((fn: (l: WxLayers) => WxLayers) => setLayersRaw(fn), [])

  return { load, t, setT, playing, setPlaying, step, snapshot, layers, setLayers }
}
