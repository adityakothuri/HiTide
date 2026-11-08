import { test } from '@playwright/test'

const OUT = process.env.SHOTS_DIR ?? '../vault/Experiments/screenshots'

test('gallery screenshots', async ({ page }) => {
  for (const [w, h] of [[1440, 900], [390, 844]] as const) {
    await page.setViewportSize({ width: w, height: h })
    await page.goto('/gallery?mode=mock')
    await page.getByText('Component gallery').waitFor()
    await page.screenshot({ path: `${OUT}/cp2-gallery-${w}x${h}.png`, fullPage: true })
  }
})
