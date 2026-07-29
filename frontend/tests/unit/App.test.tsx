import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import App from '../../src/App'
import { AppProviders } from '../../src/app/providers'
import { useRealtime } from '../../src/ws/useRealtime'
import { setupMswServer } from './helpers/msw'
import { createPageQueryClient } from './helpers/render'

// 隔离 WS 副作用：App 装配测试只验证「渲染路由外壳 + 接线 useRealtime」，
// 实时层行为由 tests/unit/ws/ 各测试专门覆盖。
vi.mock('../../src/ws/useRealtime', () => ({ useRealtime: vi.fn() }))

const ok = (data?: unknown) => HttpResponse.json({ code: 0, message: '', data })

setupMswServer(
  http.get('*/api/v1/tasks/data', () =>
    ok({ total: 0, page: 1, size: 20, tasks: [] }),
  ),
  http.get('*/api/v1/app/status', () =>
    ok({ started: true, task_count: 0, recording_count: 0 }),
  ),
)

describe('App', () => {
  it('渲染路由外壳（品牌 bili-rec）', async () => {
    render(
      <AppProviders queryClient={createPageQueryClient()}>
        <App />
      </AppProviders>,
    )
    await waitFor(() => expect(screen.getByText('bili-rec')).toBeTruthy())
  })

  it('挂载即接线实时推送（useRealtime，§7.3）', () => {
    render(
      <AppProviders queryClient={createPageQueryClient()}>
        <App />
      </AppProviders>,
    )
    expect(vi.mocked(useRealtime)).toHaveBeenCalled()
  })
})
