/**
 * Drone sample images. Live mode serves them from the backend (/static/drone/..., proxied by Vite).
 * The offline demo bundles copies under /drone/. Only same-origin /static/drone paths are trusted.
 */
export function droneImage(url: string, kind: 'live' | 'mock'): string {
  const file = url.split('/').pop() ?? ''
  if (kind === 'live' && url.startsWith('/static/drone/')) return url
  return `/drone/${file}`
}
