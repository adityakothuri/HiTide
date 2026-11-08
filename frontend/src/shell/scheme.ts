import { useSyncExternalStore } from 'react'

/** Console color scheme: light analyst (default) or night operations. Persisted per browser. */
export type Scheme = 'light' | 'dark'

const KEY = 'fw-scheme'
const listeners = new Set<() => void>()

function read(): Scheme {
  try {
    const q = new URLSearchParams(window.location.search).get('scheme')
    if (q === 'light' || q === 'dark') return q
    return window.localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

let current: Scheme = typeof window === 'undefined' ? 'light' : read()

export function setScheme(next: Scheme): void {
  current = next
  try {
    window.localStorage.setItem(KEY, next)
  } catch {
    /* Private mode: the choice lasts for this page only. */
  }
  for (const l of listeners) l()
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export function useScheme(): Scheme {
  return useSyncExternalStore(subscribe, () => current, () => 'light')
}
