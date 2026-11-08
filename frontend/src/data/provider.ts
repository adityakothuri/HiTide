import type { DroneCommand, Feeds, Reply, Town, WsEvent } from './types'

export type ConnectionStatus = 'connecting' | 'live' | 'reconnecting' | 'offline_demo'

export interface DataProvider {
  readonly kind: 'live' | 'mock'
  /** Starts the stream. Calls onEvent for every envelope, onStatus when the connection changes. */
  connect(onEvent: (e: WsEvent) => void, onStatus: (s: ConnectionStatus) => void): void
  disconnect(): void
  getTown(): Promise<Town>
  getFeeds(): Promise<Feeds>
  reply(caseId: string, reply: Reply): Promise<void>
  droneCommand(droneId: string, caseId: string, cmd: DroneCommand): Promise<void>
  startDemo(): Promise<void>
  nextStep(): Promise<void>
  reset(): Promise<void>
}
