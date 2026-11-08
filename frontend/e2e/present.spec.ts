import { test } from '@playwright/test'

const OUT = process.env.SHOTS_DIR ?? '../vault/Experiments/screenshots'

async function toStep(page: import('@playwright/test').Page, n: number) {
  for (let i = 0; i < n; i += 1) {
    await page.evaluate(() => (window as unknown as { __floodwatch: { provider: { nextStep(): Promise<void> } } }).__floodwatch.provider.nextStep())
  }
  await page.waitForTimeout(1500)
}

test('present mode', async ({ page }) => {
  for (const [w, h] of [[1920, 1080], [1440, 900]] as const) {
    await page.setViewportSize({ width: w, height: h })
    await page.goto('/present?mode=mock')
    await page.getByRole('navigation', { name: 'App sections' }).waitFor()
    await toStep(page, 2)
    await page.screenshot({ path: `${OUT}/cp5-present-${w}-step2.png` })
    await toStep(page, 2)
    await page.screenshot({ path: `${OUT}/cp5-present-${w}-step4.png` })
    await toStep(page, 3)
    await page.keyboard.press('Shift+D')
    await page.getByText('Demo controls').waitFor()
    await page.screenshot({ path: `${OUT}/cp5-present-${w}-step7.png` })
  }
})
