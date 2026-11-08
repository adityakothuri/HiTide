import type { ConnectionStatus, DataProvider } from './provider'
import { caseAfterDroneCommand } from './synthetic'
import { loadStaticTown } from './town'
import type { Case, DroneCommand, Feeds, Reply, Town, WsEvent } from './types'

const BACKOFF_MIN_MS = 500
const BACKOFF_MAX_MS = 8000

function wsUrl(): string {
  const env = import.meta.env.VITE_WS_URL as string | undefined
  if (env) return env
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws`
}

async function post(path: string, body?: unknown): Promise<Response> {
  const res = await fetch(path, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${path} returned ${res.status}`)
  return res
}

/** Live backend over the Vite proxy: WS stream plus REST actions. Reconnects with jittered backoff. */
export class WsProvider implements DataProvider {
  readonly kind = 'live' as const
  private ws: WebSocket | null = null
  private backoff = BACKOFF_MIN_MS
  private closed = false
  private retryTimer: number | null = null
  private onEvent: (e: WsEvent) => void = () => {}
  private onStatus: (s: ConnectionStatus) => void = () => {}
  private cases = new Map<string, Case>()

  connect(onEvent: (e: WsEvent) => void, onStatus: (s: ConnectionStatus) => void): void {
    this.onEvent = onEvent
    this.onStatus = onStatus
    this.closed = false
    this.open('connecting')
  }

  disconnect(): void {
    this.closed = true
    if (this.retryTimer) window.clearTimeout(this.retryTimer)
    this.retryTimer = null
    const ws = this.ws
    this.ws = null
    if (ws) {
      ws.onopen = ws.onmessage = ws.onclose = null
      ws.close()
    }
  }

  async getTown(): Promise<Town> {
    try {
      const res = await fetch('/api/town')
      if (!res.ok) throw new Error(`/api/town returned ${res.status}`)
      return (await res.json()) as Town
    } catch {
      return loadStaticTown()
    }
  }

  async getFeeds(): Promise<Feeds> {
    const res = await fetch('/api/feeds')
    if (!res.ok) throw new Error(`Feed status returned ${res.status}`)
    return (await res.json()) as Feeds
  }

  async reply(caseId: string, reply: Reply): Promise<void> {
    await post(`/api/cases/${encodeURIComponent(caseId)}/reply`, { reply })
  }

  async droneCommand(droneId: string, caseId: string, cmd: DroneCommand): Promise<void> {
    try {
      await post(`/api/drones/${encodeURIComponent(droneId)}/command`, { command: cmd })
    } catch {
      // Proposed endpoint not implemented yet: show it locally, labelled simulated.
      const c = this.cases.get(caseId)
      if (c) this.dispatchLocal(caseAfterDroneCommand(c, cmd))
    }
  }

  async startDemo(): Promise<void> {
    await post('/api/demo/start')
  }

  async nextStep(): Promise<void> {
    // The backend scenario runs on its own clock; there is no step endpoint.
  }

  async reset(): Promise<void> {
    await post('/api/demo/reset')
  }

  private dispatchLocal(c: Case): void {
    this.onEvent({ type: 'case.update', seq: -1, ts: new Date().toISOString(), payload: c })
  }

  private open(status: ConnectionStatus): void {
    this.onStatus(status)
    const ws = new WebSocket(wsUrl())
    this.ws = ws
    // Every handler checks it still owns the current socket, so a socket closed by a
    // StrictMode remount or a reconnect can never schedule another reconnect.
    ws.onopen = () => {
      if (this.ws !== ws) return
      this.backoff = BACKOFF_MIN_MS
      this.onStatus('live')
    }
    ws.onmessage = (m) => {
      if (this.ws !== ws) return
      try {
        const e = JSON.parse(m.data as string) as WsEvent
        if (e.type === 'snapshot') {
          this.cases = new Map(e.payload.cases.map((c) => [c.id, c]))
        }
        if (e.type === 'case.update') this.cases.set(e.payload.id, e.payload)
        this.onEvent(e)
      } catch (err) {
        console.error('HiTide: could not read a message from the backend', err)
      }
    }
    ws.onclose = () => {
      if (this.closed || this.ws !== ws) return
      const wait = Math.min(BACKOFF_MAX_MS, this.backoff) * (0.75 + Math.random() * 0.5)
      this.backoff = Math.min(BACKOFF_MAX_MS, this.backoff * 2)
      this.retryTimer = window.setTimeout(() => this.open('reconnecting'), wait)
      this.onStatus('reconnecting')
    }
  }
}
