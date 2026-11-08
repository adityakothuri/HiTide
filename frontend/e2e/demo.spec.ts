import { expect, test, type Page } from '@playwright/test'

// Full scripted scenario in /present (offline data): phone and console stay in step.

async function next(page: Page) {
  await page.evaluate(() => (window as unknown as { __floodwatch: { provider: { nextStep(): Promise<void> } } }).__floodwatch.provider.nextStep())
  await page.waitForTimeout(300)
}

test('the seven-step demo runs end to end', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.setViewportSize({ width: 1920, height: 1080 })
  await page.goto('/present?mode=mock')
  const phone = page.getByRole('complementary', { name: 'Driver app' })
  await expect(phone.getByText(/Flood Watch is on/)).toBeVisible()

  await next(page) // 1: warning issued
  await next(page) // 2: pre-trip text to Dana
  await expect(phone.getByRole('button', { name: 'Use safer route' })).toBeVisible()
  await phone.getByRole('button', { name: 'Use safer route' }).click()
  await expect(phone.getByRole('button', { name: 'Using safer route' })).toBeVisible()

  await next(page) // 3: Luis drives toward the flooded crossing
  await expect(phone.getByRole('alertdialog')).toContainText('Turn around')
  await phone.getByRole('button', { name: 'Show new route' }).click()
  await expect(phone.getByText('You turned around. Here is your new route.')).toBeVisible()

  await next(page) // 4: Margaret stalls, Flood Watch calls
  await expect(phone.getByRole('button', { name: 'Answer call' })).toBeVisible()
  await expect(page.getByText('Margaret', { exact: false }).first()).toBeVisible()
  await phone.getByRole('button', { name: 'Decline call' }).click()
  await expect(phone.getByText('Are you safe?')).toBeVisible()

  await next(page) // 5: family contacted
  await next(page) // 6: drone dispatched
  await expect(phone.getByText('Help is on the way')).toBeVisible()
  // The console opens a case's detail only when the operator selects it.
  await page.locator('[data-case]').first().click()
  await expect(page.getByRole('heading', { name: 'Drone', exact: true })).toBeVisible()

  await next(page) // 7: verified, handed to responders
  await expect(phone.getByText('Rescue team notified')).toBeVisible()
  await page.screenshot({ path: '../vault/Experiments/screenshots/e2e-demo-final.png' })
  expect(errors).toEqual([])
})
