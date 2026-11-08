import { useEffect, useState } from 'react'
import type { Town } from '../data/types'
import { useStore } from '../state/StoreContext'

export type TownState = { status: 'loading' } | { status: 'ready'; town: Town } | { status: 'error'; message: string }

import type { DataProvider } from '../data/provider'

const cache = new WeakMap<DataProvider, Promise<Town>>()

/** Loads the static town once per page (backend /api/town when live, bundled cache otherwise). */
export function useTown(): { state: TownState; retry: () => void } {
  const store = useStore()
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<TownState>({ status: 'loading' })

  useEffect(() => {
    let alive = true
    let pending = cache.get(store.provider)
    if (!pending) {
      pending = store.provider.getTown()
      cache.set(store.provider, pending)
    }
    pending.then(
      (town) => alive && setState({ status: 'ready', town }),
      (err: unknown) => {
        cache.delete(store.provider)
        if (alive) setState({ status: 'error', message: err instanceof Error ? err.message : 'Unknown error' })
      },
    )
    return () => {
      alive = false
    }
  }, [store, attempt])

  return { state, retry: () => { setState({ status: 'loading' }); setAttempt((a) => a + 1) } }
}
