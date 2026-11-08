import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { loadLiveSource } from './liveSource'
import { loadReplaySource } from './replaySource'
import type { RainProduct, WxMode, WxSnapshot, WxSource } from './types'

/** One step per tick while playing: 6.5 h of replay in about 20 s. */
const PLAY_TICK_MS = 250

export interface WxLayers { rain: RainProduct | null; depth: boolean; gauges: boolean; roads: boolean }

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

const MODE: WxMode = import.meta.env.VITE_WX_MODE === 'live' ? 'live' : 'replay'

/** Optional `?t=2025-07-04T09:30:00Z` starts the replay at that time (used for screenshots). */
function initialT(range: [number, number]): number {
  const q = new URLSearchParams(window.location.search).get('t')
  const ms = q ? Date.parse(q) : NaN
  return Number.isFinite(ms) ? Math.min(range[1], Math.max(range[0], ms)) : range[0]
}

export function useWx(): WxState {
  const [load, setLoad] = useState<WxLoad>({ status: 'loading' })
  const [t, setTRaw] = useState(0)
  const [playing, setPlaying] = useState(false)
  const tRef = useRef(t)
  useEffect(() => {
    tRef.current = t
  }, [t])
  const [layers, setLayersRaw] = useState<WxLayers>({ rain: 'p1h', depth: true, gauges: true, roads: true })

  useEffect(() => {
    let alive = true
    ;(MODE === 'live' ? loadLiveSource() : loadReplaySource()).then(
      (source) => {
        if (!alive) return
        setLoad({ status: 'ready', source })
        setTRaw(initialT(source.range))
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
