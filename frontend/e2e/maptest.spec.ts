import { expect, test } from '@playwright/test'

const OUT = process.env.SHOTS_DIR ?? '../vault/Experiments/screenshots'

// The phone's warning screen uses a MiniMap; the console uses the full map. Both must render
// on real tiles and on the offline fallback when the basemap host is unreachable.
test('basemap renders, and falls back offline', async ({ page, browser }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/console?mode=mock')
  await expect(page.locator('.maplibregl-canvas').first()).toBeVisible()
  await page.waitForTimeout(4000)
  await page.screenshot({ path: `${OUT}/r3-map-tiles.png` })

  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const off = await ctx.newPage()
  await off.route(/cartocdn/, (r) => r.abort())
  await off.goto('/console?mode=mock')
  await off.waitForTimeout(6500)
  await expect(off.locator('.maplibregl-canvas').first()).toBeVisible()
  await off.screenshot({ path: `${OUT}/r3-map-offline.png` })
  await ctx.close()
})
