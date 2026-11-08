import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { TexasMonitor } from './TexasMonitor'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function record(id: string, properties: object) {
  return { source_record_id: id, attempt_id: 'a', raw_payload: { properties, geometry: { type: 'Point', coordinates: [-95.37, 29.76] } } }
}

it('shows partial statewide coverage, road remarks and only observations inside the selected window', async () => {
  const now = new Date().toISOString()
  const old = new Date(Date.now() - 45 * 60_000).toISOString()
  const snapshot = (minutes: number) => ({
    scope: 'texas', as_of: now, max_age_minutes: minutes, sources: {
      nws_local_storm_reports: { status: 'partial', records: [record('road', { valid: now, city: 'Houston', county: 'Harris', remark: 'Water over Main Street.' })], excluded: {} },
      usgs_gage: { status: 'complete', records: [record('old', { time: old, monitoring_location_id: 'Old station' })], excluded: {} },
    },
  })
  const fetcher = vi.fn(async (url: string) => new Response(JSON.stringify(snapshot(url.endsWith('15') ? 15 : 30))))
  vi.stubGlobal('fetch', fetcher)
  render(<TexasMonitor />)
  const item = await screen.findByRole('button', { name: /Houston.*Harris County.*Main Street/ })
  expect(screen.getByText('Partial results')).toBeDefined()
  expect(screen.getByText('Source unavailable')).toBeDefined()
  expect(screen.queryByText('Old station')).toBeNull()
  fireEvent.click(item)
  expect(screen.getByRole('button', { name: 'Clear selection' })).toBeDefined()
  fireEvent.change(screen.getByLabelText('Observation window'), { target: { value: '15' } })
  await screen.findByRole('button', { name: /Harris County/ })
  expect(fetcher).toHaveBeenCalledWith('/api/feeds/recent?max_age_minutes=15', expect.anything())
  fireEvent.change(screen.getByLabelText('Find a location'), { target: { value: 'Dallas' } })
  expect(screen.getByText(/Coverage is incomplete/)).toBeDefined()
})

it('rejects a local or malformed snapshot returned for the statewide query', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ scope: 'kerrville', max_age_minutes: 30, sources: {} }))))
  render(<TexasMonitor />)
  expect((await screen.findByRole('alert')).textContent).toContain('Texas feed unavailable')
})
