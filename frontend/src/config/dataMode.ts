/**
 * Test data vs real data, in one place.
 *
 * Precedence: `?data=test|real` in the URL > VITE_DATA_MODE (set by ./dev.sh) > what the backend reports
 * at /api/health. The backend is the source of truth for feeds and outreach; the frontend only uses the
 * mode to pick the weather layer source and to label the screen.
 */
export type DataMode = 'test' | 'real'

export interface BackendModes {
  data_mode: string
  outreach: 'mock' | 'stable' | 'photon2'
  feeds: 'cache' | 'live'
  region: string
  db: string
}

function parse(v: unknown): DataMode | null {
  return v === 'test' || v === 'real' ? v : null
}

/** Mode forced by the URL or the build env, or null to ask the backend. */
export function forcedDataMode(): DataMode | null {
  return parse(new URLSearchParams(window.location.search).get('data')) ?? parse(import.meta.env.VITE_DATA_MODE)
}

let modesPromise: Promise<BackendModes | null> | null = null

/** Backend modes from /api/health, fetched once per page load. null when the backend is unreachable. */
export function backendModes(): Promise<BackendModes | null> {
  modesPromise ??= fetch('/api/health')
    .then((r) => (r.ok ? r.json() : null))
    .then((h: { modes?: BackendModes } | null) => h?.modes ?? null)
    .catch(() => null)
  return modesPromise
}

export async function dataMode(): Promise<DataMode> {
  return forcedDataMode() ?? parse((await backendModes())?.data_mode) ?? 'test'
}
