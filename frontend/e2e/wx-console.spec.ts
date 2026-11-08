import { expect, test } from '@playwright/test'

/**
 * Weather and flood console at 1440x900, offline replay of July 4, 2025. Saves screenshots for design review.
 * Times are UTC: 07:00Z = 02:00 CDT, 09:30Z = 04:30 CDT, 11:30Z = 06:30 CDT.
 */
const SHOTS = '../vault/Experiments/screenshots'
const TIMES = [
  ['0200', '2025-07-04T07:00:00Z'],
  ['0430', '2025-07-04T09:30:00Z'],
  ['0630', '2025-07-04T11:30:00Z'],
] as const

test.use({ viewport: { width: 1440, height: 900 } })

for (const [label, iso] of TIMES) {
  test(`console at ${label} CDT`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    await page.goto(`/console?mode=mock&t=${iso}`)
    await expect(page.getByRole('group', { name: 'Map key' })).toBeVisible()
    await expect(page.getByRole('slider', { name: 'Replay time' })).toBeVisible()
    await mapIdle(page)
    await page.screenshot({ path: `${SHOTS}/wx-console-${label}.png` })
    expect(errors).toEqual([])
  })
}

test('gauge detail on click', async ({ page }) => {
  await page.goto('/console?mode=mock&t=2025-07-04T11:30:00Z')
  await expect(page.getByRole('group', { name: 'Map key' })).toBeVisible()
  await mapIdle(page)
  // Click the Kerrville gauge (USGS 08166200) at its projected position.
  await page.locator('canvas.maplibregl-canvas').click({ position: await gaugePosition(page) })
  await expect(page.getByRole('complementary', { name: 'Gauge detail' })).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/wx-console-gauge.png` })
})

async function gaugePosition(page: import('@playwright/test').Page): Promise<{ x: number; y: number }> {
  return page.evaluate(() => {
    const w = window as unknown as { __flMap?: { project: (ll: [number, number]) => { x: number; y: number } } }
    const p = w.__flMap?.project([-99.1633749852236, 30.0532660119763])
    if (!p) throw new Error('map handle missing')
    return { x: p.x, y: p.y }
  })
}

/** Waits until MapLibre has the basemap and raster tiles for the current view. */
async function mapIdle(page: import('@playwright/test').Page): Promise<void> {
  await page.waitForFunction(() => {
    const m = (window as unknown as { __flMap?: { loaded: () => boolean; areTilesLoaded: () => boolean } }).__flMap
    return !!m && m.loaded() && m.areTilesLoaded()
  }, undefined, { timeout: 30_000 })
  await page.waitForTimeout(500)
}
