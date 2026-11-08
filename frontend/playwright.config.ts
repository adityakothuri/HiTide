import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 180_000,
  // One worker: several WebGL maps at once slow the browser enough to race the demo's real-time timers.
  workers: 1,
  use: { baseURL: 'http://localhost:5173' },
  webServer: { command: 'npm run dev -- --port 5173 --strictPort', url: 'http://localhost:5173', reuseExistingServer: true },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
