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
  expect(screen.getAllByText('Source unavailable').length).toBeGreaterThan(0)
  expect(screen.queryByText('Old station')).toBeNull()
  fireEvent.click(item)
  expect(screen.getByRole('button', { name: 'Clear selection' })).toBeDefined()
  fireEvent.change(screen.getByLabelText('Observation window'), { target: { value: '15' } })
  await screen.findByRole('button', { name: /Harris County/ })
  expect(fetcher).toHaveBeenCalledWith('/api/feeds/recent?map_view=true&max_age_minutes=15', expect.anything())
  fireEvent.change(screen.getByLabelText('Find a location'), { target: { value: 'Dallas' } })
  expect(screen.getByText(/Coverage is incomplete/)).toBeDefined()
})

it('rejects a local or malformed snapshot returned for the statewide query', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ scope: 'kerrville', max_age_minutes: 30, sources: {} }))))
  render(<TexasMonitor />)
  expect((await screen.findByRole('alert')).textContent).toContain('Texas feed unavailable')
})

it('shows model previews separately from optional unknown-time camera context', async () => {
  const now = new Date().toISOString()
  const row = (id: string, time: string | null, evidence_type: string) => ({
    ...record(id, {}), preview: { title: id, detail: 'Provider detail', time,
      evidence_type, timestamp_role: time ? 'product_valid_time' : 'unknown',
      geometry: { type: 'Point', coordinates: [-95.37, 29.76] } },
  })
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
    scope: 'texas', as_of: now, max_age_minutes: 30, sources: {
      noaa_flash: { label: 'NOAA runoff guidance', status: 'complete', records: [row('Runoff cell', now, 'model')], excluded: {} },
      txdot_cameras: { label: 'TxDOT camera inventory', status: 'complete', records: [],
        context: [row('Camera location', null, 'context')], excluded: { unknown_time: 1 } },
    },
  }))))
  render(<TexasMonitor />)
  expect(await screen.findByText('Runoff cell')).toBeDefined()
  expect(screen.queryByText('Camera location')).toBeNull()
  fireEvent.click(screen.getByRole('checkbox'))
  expect(screen.getByText('Camera location')).toBeDefined()
  expect(screen.getByText(/Time unverified/)).toBeDefined()
})
