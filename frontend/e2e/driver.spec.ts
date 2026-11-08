import { test, type Page } from '@playwright/test'

const OUT = process.env.SHOTS_DIR ?? '../vault/Experiments/screenshots'
const TAG = process.env.SHOTS_TAG ?? 'cp3'

async function open(page: Page, driver: string) {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`/driver?mode=mock&driver=${driver}`)
  await page.getByRole('navigation', { name: 'App sections' }).waitFor()
}

/** Plays the recorded demo up to the end of narration step n. */
async function toStep(page: Page, n: number) {
  for (let i = 0; i < n; i += 1) {
    await page.evaluate(() => (window as unknown as { __floodwatch: { provider: { nextStep(): Promise<void> } } }).__floodwatch.provider.nextStep())
  }
  await page.waitForTimeout(400)
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${TAG}-driver-${name}.png` })

test('driver screens 5.1 to 5.7', async ({ page }) => {
  await open(page, 'demo-d')
  await shot(page, '1-home')

  await open(page, 'demo-a')
  await toStep(page, 2)
  await page.getByRole('button', { name: 'Use safer route' }).waitFor()
  await shot(page, '2a-push')
  await page.getByRole('button', { name: /Flood Watch now/ }).click()
  await shot(page, '2-warning')

  await open(page, 'demo-b')
  await toStep(page, 3)
  await page.getByRole('alertdialog').waitFor()
  await shot(page, '3-turn-around')
  await page.getByRole('button', { name: 'Show new route' }).click()
  await shot(page, '3b-new-route')

  await open(page, 'demo-d')
  await toStep(page, 4)
  await page.getByRole('button', { name: 'Answer call' }).waitFor()
  await shot(page, '4a-incoming-call')
  await page.getByRole('button', { name: 'Answer call' }).click()
  await shot(page, '4b-call-connected')
  await page.getByRole('button', { name: 'End call' }).click()
  await page.getByRole('button', { name: "I'm safe" }).waitFor()
  await shot(page, '4-check-in')

  await toStep(page, 2)
  await page.getByText('Help is on the way').waitFor()
  await shot(page, '5-help')

  await open(page, 'demo-d')
  await toStep(page, 4)
  await page.getByRole('button', { name: 'Decline call' }).click()
  await page.getByRole('button', { name: "I'm safe" }).click()
  await page.getByText("You're safe. We started your claim.").waitFor()
  await shot(page, '6-claim')

  await page.getByRole('button', { name: 'Flood Watch settings' }).click()
  await shot(page, '7-settings')
})
