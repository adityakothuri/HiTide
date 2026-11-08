import { useEffect, useMemo, useState } from 'react'
import { decodeFactors, decodeFrame, parseIndex, type RiskFrame, type RiskIndex } from './grid'

export interface LoadedFrame {
  frame: RiskFrame
  values: Float32Array
  factors: Uint8Array | null
}

export type RiskGridState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; index: RiskIndex; current: LoadedFrame | null }

const BASE = import.meta.env.BASE_URL ?? '/'
const url = (p: string) => `${BASE.replace(/\/$/, '')}/${p.replace(/^\//, '')}`

/** Latest frame at or before t; the first frame when t is earlier than all of them. */
export function frameAt(frames: readonly RiskFrame[], t: number): RiskFrame {
  let pick = frames[0]
  for (const f of frames) if (f.t <= t) pick = f
  return pick
}

async function fetchBuf(path: string): Promise<ArrayBuffer> {
  const r = await fetch(url(path))
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
  return r.arrayBuffer()
}

const cache = new Map<string, Promise<LoadedFrame>>()

function loadFrame(index: RiskIndex, frame: RiskFrame): Promise<LoadedFrame> {
  let p = cache.get(frame.id)
  if (!p) {
    p = Promise.all([fetchBuf(frame.url), fetchBuf(frame.factorsUrl).catch(() => null)]).then(([v, f]) => ({
      frame,
      values: decodeFrame(v, index.width, index.height),
      factors: f ? decodeFactors(f, index.width, index.height) : null,
    }))
    p.catch(() => cache.delete(frame.id))
    cache.set(frame.id, p)
  }
  return p
}

/** Loads public/grids/index.json once, then the frame for time t (prefetching the next one). */
export function useRiskGrid(t: number, enabled: boolean): RiskGridState & { retry: () => void } {
  const [index, setIndex] = useState<RiskIndex | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [current, setCurrent] = useState<LoadedFrame | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!enabled || index) return
    let alive = true
    fetch(url('grids/index.json'))
      .then((r) => {
        if (!r.ok) throw new Error(`Risk grid not built (HTTP ${r.status}). Run scripts.build_risk_grid.`)
        return r.json()
      })
      .then((j: unknown) => alive && (setIndex(parseIndex(j)), setError(null)))
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      alive = false
    }
  }, [enabled, index, attempt])

  const frame = useMemo(() => (index ? frameAt(index.frames, t) : null), [index, t])

  useEffect(() => {
    if (!index || !frame) return
    let alive = true
    loadFrame(index, frame).then(
      (f) => {
        if (!alive) return
        setCurrent(f)
        setError(null)
      },
      (e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)),
    )
    const next = index.frames[index.frames.indexOf(frame) + 1]
    if (next) void loadFrame(index, next).catch(() => undefined)
    return () => {
      alive = false
    }
  }, [index, frame])

  const retry = () => {
    setError(null)
    setIndex(null)
    setAttempt((a) => a + 1)
  }
  if (error) return { status: 'error', message: error, retry }
  if (!index) return { status: 'loading', retry }
  return { status: 'ready', index, current, retry }
}
