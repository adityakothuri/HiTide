import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from 'react'
import { MockProvider } from '../data/mockProvider'
import { WsProvider } from '../data/wsProvider'
import type { AppState } from './reducer'
import { createStore, type Store, type UiState } from './store'

const LIVE_TIMEOUT_MS = 2500

const StoreCtx = createContext<Store | null>(null)

export type Mode = 'live' | 'mock' | 'auto'

export function modeFromUrl(): Mode {
  const m = new URLSearchParams(window.location.search).get('mode')
  return m === 'live' || m === 'mock' ? m : 'auto'
}

/**
 * Picks the provider. "auto" tries the live backend first and falls back to the offline demo
 * only if the first connection does not open in time. It never switches mid-demo.
 */
export function StoreProvider({ children, mode = modeFromUrl() }: { children: ReactNode; mode?: Mode }) {
  const [store, setStore] = useState<Store>(() => createStore(mode === 'mock' ? new MockProvider() : new WsProvider()))

  useEffect(() => {
    store.provider.connect(
      (e) => store.dispatch(e),
      (status) => store.setUi((u) => ({ ...u, status })),
    )
    let timer: number | undefined
    if (mode === 'auto' && store.provider.kind === 'live') {
      timer = window.setTimeout(() => {
        if (store.getUi().status !== 'live') setStore(createStore(new MockProvider()))
      }, LIVE_TIMEOUT_MS)
    }
    return () => {
      window.clearTimeout(timer)
      store.provider.disconnect()
    }
  }, [store, mode])

  return <StoreCtx.Provider value={store}>{children}</StoreCtx.Provider>
}

export function useStore(): Store {
  const s = useContext(StoreCtx)
  if (!s) throw new Error('useStore must be used inside <StoreProvider>')
  return s
}

export function useApp<T>(select: (s: AppState) => T): T {
  const store = useStore()
  return useSyncExternalStore(store.subscribe, () => select(store.getApp()))
}

export function useUi<T>(select: (s: UiState) => T): T {
  const store = useStore()
  return useSyncExternalStore(store.subscribe, () => select(store.getUi()))
}
