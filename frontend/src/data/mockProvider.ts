import recording from '../demo/recording.json'
import feedsSample from '../demo/feeds.json'
import type { DataProvider, ConnectionStatus } from './provider'
import { caseAfterDroneCommand, caseAfterReply } from './synthetic'
import { loadStaticTown } from './town'
import type { Case, DroneCommand, DroneState, EventType, Feeds, Reply, Town, WsEvent } from './types'

interface Recorded { dt_ms: number; type: EventType; payload: unknown }

const RECORDED = recording as Recorded[]
const TIME_KEYS = new Set(['ts', 'opened_at', 'fetched_at', 'time'])
const FIRST_AFTER_SNAPSHOT = RECORDED.findIndex((r) => r.type === 'snapshot') + 1
const CREW_ETA_S = 17 * 60 // estimated ground-crew arrival used when the backend sends none

function shiftTimes(value: unknown, offsetMs: number): unknown {
  if (Array.isArray(value)) return value.map((v) => shiftTimes(v, offsetMs))
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => {
        if (TIME_KEYS.has(k) && typeof v === 'string' && !Number.isNaN(Date.parse(v))) {
          return [k, new Date(Date.parse(v) + offsetMs).toISOString()]
        }
        return [k, shiftTimes(v, offsetMs)]
      }),
    )
  }
  return value
}

function firstRecordedTime(): number {
  for (const r of RECORDED) {
    const ts = (r.payload as { ts?: string; opened_at?: string }).ts ?? (r.payload as { opened_at?: string }).opened_at
    if (ts && !Number.isNaN(Date.parse(ts))) return Date.parse(ts) - r.dt_ms
  }
  return Date.now()
}

/** Replays a recorded run of the backend demo with the same envelopes, re-timed to now. */
export class MockProvider implements DataProvider {
  readonly kind = 'mock' as const
  private onEvent: (e: WsEvent) => void = () => {}
  private timers: number[] = []
  private seq = 0
  private cursor = FIRST_AFTER_SNAPSHOT
  private startedAt = 0
  private offsetMs = 0
  private cases = new Map<string, Case>()
  private lastDroneState = new Map<string, DroneState>()
  private firstEta = new Map<string, number>()
  private readonly recordedStart = firstRecordedTime()

  connect(onEvent: (e: WsEvent) => void, onStatus: (s: ConnectionStatus) => void): void {
    this.onEvent = onEvent
    onStatus('offline_demo')
    this.emitSnapshot()
  }

  disconnect(): void {
    this.clearTimers()
  }

  async getTown(): Promise<Town> {
    return loadStaticTown()
  }

  async getFeeds(): Promise<Feeds> {
    return shiftTimes(feedsSample, Date.now() - Date.parse((feedsSample as Feeds).nws_alerts?.fetched_at ?? new Date().toISOString())) as Feeds
  }

  async reply(caseId: string, reply: Reply): Promise<void> {
    const c = this.cases.get(caseId)
    if (c) this.emit('case.update', caseAfterReply(c, reply))
  }

  async droneCommand(droneId: string, caseId: string, cmd: DroneCommand): Promise<void> {
    const c = this.cases.get(caseId)
    if (c) this.emit('case.update', caseAfterDroneCommand(c, cmd))
    const d = this.lastDroneState.get(droneId)
    if (cmd === 'return' && d) this.emit('drone.update', { ...d, status: 'returning' })
  }

  async startDemo(): Promise<void> {
    this.reset()
    this.startedAt = Date.now()
    this.offsetMs = this.startedAt - this.recordedStart
    this.scheduleFrom(FIRST_AFTER_SNAPSHOT)
  }

  /** Jump straight to the next narration step. */
  async nextStep(): Promise<void> {
    if (this.startedAt === 0) await this.startDemo()
    if (this.cursor >= RECORDED.length) return
    this.clearTimers()
    let i = this.cursor
    do {
      this.play(RECORDED[i], i)
      i += 1
    } while (i < RECORDED.length && RECORDED[i].type !== 'demo.step')
    // Re-anchor time so the rest of the script continues from here.
    const nextDt = RECORDED[i]?.dt_ms ?? 0
    this.startedAt = Date.now() - nextDt
    this.offsetMs = this.startedAt - this.recordedStart
    this.scheduleFrom(i)
  }

  async reset(): Promise<void> {
    this.clearTimers()
    this.cursor = FIRST_AFTER_SNAPSHOT
    this.startedAt = 0
    this.cases.clear()
    this.firstEta.clear()
    this.lastDroneState.clear()
    this.emitSnapshot()
  }

  private scheduleFrom(start: number): void {
    for (let i = start; i < RECORDED.length; i += 1) {
      const r = RECORDED[i]
      const delay = Math.max(0, this.startedAt + r.dt_ms - Date.now())
      this.timers.push(window.setTimeout(() => this.play(r, i), delay))
    }
  }

  private play(r: Recorded, index: number): void {
    this.cursor = index + 1
    let payload = shiftTimes(r.payload, this.offsetMs)
    if (r.type === 'drone.update') payload = this.withCrewEta(payload as DroneState)
    this.emit(r.type, payload)
  }

  private withCrewEta(d: DroneState): DroneState {
    if (d.crew_eta_s != null) return d
    const first = this.firstEta.get(d.id) ?? d.eta_s
    this.firstEta.set(d.id, first)
    return { ...d, crew_eta_s: Math.max(0, CREW_ETA_S - (first - d.eta_s)) }
  }

  private emitSnapshot(): void {
    const snap = RECORDED.find((r) => r.type === 'snapshot')
    if (snap) this.emit('snapshot', snap.payload)
  }

  private emit(type: EventType, payload: unknown): void {
    this.seq += 1
    if (type === 'case.update') this.cases.set((payload as Case).id, payload as Case)
    if (type === 'drone.update') this.lastDroneState.set((payload as DroneState).id, payload as DroneState)
    this.onEvent({ type, seq: this.seq, ts: new Date().toISOString(), payload } as WsEvent)
  }

  private clearTimers(): void {
    this.timers.forEach((t) => window.clearTimeout(t))
    this.timers = []
  }
}
