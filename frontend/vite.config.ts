import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// 开发期通过代理把 /api 与 /ws 转发到本地后端（默认 :2233），
// 前后端可独立热更（见 frontend-design.md §4/§12）。
const BACKEND = process.env.VITE_BACKEND ?? 'http://127.0.0.1:2233'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND, changeOrigin: true, ws: true },
    },
  },
  // 单测：jsdom 环境 + 全局 API（见 frontend-design.md §10.3）。
  // 覆盖率门禁全局 ≥80%；生成物与入口壳不计入统计。
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['tests/unit/setup.ts'],
    include: ['tests/unit/**/*.test.{ts,tsx}'],
    // AntD 重型页面（多分组表单）在 CI 较慢，放宽超时避免偶发超时抖动。
    testTimeout: 15000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json-summary'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx', 'src/**/*.d.ts', 'src/api/schema.d.ts'],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 80,
        statements: 80,
      },
    },
  },
})
