import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E 配置（frontend-design.md §10.2/§11.2）。
 *
 * - testDir 独立于单测（tests/unit 由 Vitest 收集，见 vite.config.ts）。
 * - webServer 用 `pnpm preview` 托管 `pnpm build` 产物（需先 build）；
 *   E2E 通过 page.route 拦截 REST、addInitScript 注入 WebSocket，
 *   实现无需真实后端的确定性旅程测试（§10.3 确定性要求）。
 * - 浏览器可经 PLAYWRIGHT_BROWSERS_PATH 指定缓存目录（沙箱/离线镜像）。
 */
const PORT = Number(process.env.E2E_PORT ?? 4173)

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [['github'], ['html', { open: 'never' }]]
    : [['list']],
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `pnpm preview --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
