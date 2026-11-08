import type { ConnectionStatus, DataProvider } from '../data/provider'
import type { Reply, WsEvent } from '../data/types'
import { initialState, reduceEvent, type AppState } from './reducer'

/** UI-only flags that never come from the backend. */
export interface UiState {
  status: ConnectionStatus
  replies: Record<string, Reply>              // caseId -> reply sent from the driver app
  turnDismissed: Record<string, boolean>      // driverId -> tapped "Show new route"
  routeAccepted: Record<string, boolean>      // driverId -> tapped "Use safer route"
  remindLater: Record<string, boolean>        // driverId -> tapped "Remind me later"
  selectedCaseId: string | null
}

export interface Store {
  getApp(): AppState
  getUi(): UiState
  subscribe(fn: () => void): () => void
  dispatch(e: WsEvent): void
  setUi(patch: (ui: UiState) => UiState): void
  provider: DataProvider
}

export const initialUi: UiState = {
  status: 'connecting',
  replies: {},
  turnDismissed: {},
  routeAccepted: {},
  remindLater: {},
  selectedCaseId: null,
}

export function createStore(provider: DataProvider): Store {
  let app = initialState
  let ui = initialUi
  const subs = new Set<() => void>()
  const notify = () => subs.forEach((fn) => fn())

  return {
    provider,
    getApp: () => app,
    getUi: () => ui,
    subscribe(fn) {
      subs.add(fn)
      return () => subs.delete(fn)
    },
    dispatch(e) {
      const next = reduceEvent(app, e)
      if (next === app) return
      // The sim was reset: clear driver-side choices too.
      if (next.epoch !== app.epoch) ui = { ...initialUi, status: ui.status }
      app = next
      notify()
    },
    setUi(patch) {
      ui = patch(ui)
      notify()
    },
  }
}
