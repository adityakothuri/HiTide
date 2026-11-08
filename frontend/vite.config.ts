/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  // Shell env wins over frontend/.env (loadEnv merges process.env last for matching keys).
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env }
  const backend = env.VITE_BACKEND_URL ?? 'http://localhost:8000'
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': backend,
        '/static': backend,
        '/ws': { target: backend.replace(/^http/, 'ws'), ws: true },
      },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    },
  }
})
