import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Operations } from './Operations'

vi.mock('./ops/EvidenceMap', () => ({ EvidenceMap: () => null }))

const initial = {
  generated_at: '2026-11-08T01:00:00Z', dataset: { id: 'demo', name: 'Two-exit neighborhood', simulated: true },
  roads: [{ id: 'exit-b', name: 'Exit B crossing', geometry: { type: 'LineString', coordinates: [[-99.14, 30.04], [-99.13, 30.05]] }, access: 'unknown', freshness: 'stale', agreement: 'consistent', evidence_ids: ['old'] }],
  observations: [{ id: 'old', source_id: 'local_reports', observed_at: '2026-11-08T00:00:00Z', ingested_at: '2026-11-08T00:30:00Z', kind: 'report', road_id: 'exit-b', access: 'open', quality: 'unverified', simulated: true, raw: { description: 'Earlier report' } }],
  tasks: [{ id: 'inspect-b', road_id: 'exit-b', road_name: 'Exit B crossing', status: 'queued', priority: 100, reasons: ['Last remaining possible exit'], affected_communities: ['Neighborhood A'] }],
  communities: [{ id: 'a', name: 'Neighborhood A', node_id: 'home', optimistic_access: true, conservative_access: false, remaining_exits: 1 }], sources: [],
}

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('operations evidence workflow', () => {
  it('shows provenance and keeps observation time separate from receipt time', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(initial))))
    render(<Operations />)
    await screen.findByRole('heading', { name: 'Road verification' })
    await screen.findByText('Last remaining possible exit')
    fireEvent.click(screen.getByRole('button', { name: /Exit B crossing/ }))
    expect(screen.getByRole('heading', { name: 'Exit B crossing' })).toBeDefined()
    expect(screen.getByText(/^Observed .* · received /)).toBeDefined()
    expect(screen.getByText('Earlier report')).toBeDefined()
    expect(screen.getByText('1 modeled exit remaining')).toBeDefined()
    expect(screen.getByText('Only modeled exit · Neighborhood A')).toBeDefined()
  })

  it('assigns a task then records a simulated closed inspection and refreshes connectivity', async () => {
    let assigned = false
    let closed = false
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith('/assign')) assigned = true
      if (url.endsWith('/complete')) {
        expect(JSON.parse(String(options?.body)).outcome).toBe('closed')
        closed = true
      }
      const snapshot = { ...initial, tasks: [{ ...initial.tasks[0], status: closed ? 'completed' : assigned ? 'assigned' : 'queued' }], communities: [{ ...initial.communities[0], optimistic_access: !closed }] }
      return new Response(JSON.stringify(snapshot))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<Operations />)
    fireEvent.click(await screen.findByRole('button', { name: 'Assign inspection' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Record simulated inspection' }))
    await waitFor(() => expect(screen.getByText('Inspection recorded. Road evidence and priorities recomputed.')).toBeDefined())
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/complete'))).toBe(true)
  })

  it('shows connection errors instead of substituting demonstration evidence', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Backend offline')))
    render(<Operations />)
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(screen.queryByText('Neighborhood A')).toBeNull()
  })
})
