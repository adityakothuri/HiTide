/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const BACKEND = process.env.VITE_BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api/live-drone': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        rewrite: path => {
          const bridgePath = path.replace('/api/live-drone', '')
          return bridgePath === '/gauge' ? '/gauge/status' : bridgePath
        },
        headers: { Origin: 'http://127.0.0.1:8765' },
      },
      '/api': BACKEND,
      '/static': BACKEND,
      '/ws': { target: BACKEND.replace(/^http/, 'ws'), ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
})
