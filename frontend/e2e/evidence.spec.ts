import { expect, test } from '@playwright/test'

test('inspection evidence changes neighborhood connectivity and survives a reload', async ({ page }) => {
  let started = false
  let assigned = false
  let completed = false
  const observed = new Date().toISOString()
  const snapshot = () => ({
    generated_at: observed, dataset: { id: started ? 'demo' : 'town', name: started ? 'Two-exit neighborhood' : 'Kerrville roads', simulated: started },
    roads: [{ id: 'exit-b', name: 'Exit B crossing', geometry: { type: 'LineString', coordinates: [[-99.14, 30.04], [-99.13, 30.05]] }, access: completed ? 'closed' : 'unknown', freshness: completed ? 'current' : 'stale', agreement: 'consistent', evidence_ids: ['report'] }],
    observations: [{ id: 'report', source_id: completed ? 'drone' : 'local_reports', observed_at: observed, ingested_at: observed, kind: completed ? 'drone' : 'report', road_id: 'exit-b', access: completed ? 'closed' : 'unknown', quality: 'operator', simulated: true, raw: { description: completed ? 'Flooding verified' : 'Old crossing report' } }],
    tasks: started ? [{ id: 'inspect-b', road_id: 'exit-b', road_name: 'Exit B crossing', status: completed ? 'completed' : assigned ? 'assigned' : 'queued', priority: 100, reasons: ['Only remaining possible exit'], affected_communities: ['Neighborhood A'] }] : [],
    communities: started ? [{ id: 'a', name: 'Neighborhood A', node_id: 'home', optimistic_access: !completed, conservative_access: false, remaining_exits: completed ? 0 : 1 }] : [], sources: [],
  })
  await page.route('**/api/evidence/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/demo')) started = true
    if (path.endsWith('/assign')) assigned = true
    if (path.endsWith('/complete')) {
      expect(route.request().postDataJSON().outcome).toBe('closed')
      completed = true
    }
    await route.fulfill({ json: snapshot() })
  })
  await page.goto('/console')
  await expect(page.getByRole('heading', { name: 'Flood intelligence' })).toBeVisible()
  await page.getByRole('button', { name: 'Load two-exit demo' }).click()
  await expect(page.getByText('Only remaining possible exit')).toBeVisible()
  await page.getByRole('button', { name: 'Assign inspection' }).click()
  await page.getByRole('button', { name: 'Record simulated inspection' }).click()
  await expect(page.getByText('No modeled exit', { exact: true })).toBeVisible()
  await expect(page.getByText('Flooding verified')).toBeVisible()
  await page.reload()
  await expect(page.getByText('No modeled exit', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('heading', { name: 'Flood intelligence' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('unavailable backend is explicit and never creates fake evidence', async ({ page }) => {
  await page.route('**/api/evidence/**', (route) => route.fulfill({ status: 503, json: { detail: 'Service unavailable' } }))
  await page.goto('/console')
  await expect(page.getByRole('alert')).toContainText('No demonstration data has been substituted')
  await expect(page.getByRole('heading', { name: 'Community access' })).toHaveCount(0)
})
