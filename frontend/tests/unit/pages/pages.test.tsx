/**
 * M30 DT：布局外壳 + 路由 + 任务列表/详情/添加 + Dashboard（§8/§14.4-§14.6）。
 * 用内存路由装配真实 routes，MSW 依契约提供响应。
 * 注：AntD 在两个中文字符按钮间插入空格，涉及双字按钮以正则匹配。
 */
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { activeNavKey } from '../../../src/layouts/AppLayout'
import { makeTaskDataRaw, makeTasksPageResponse } from '../helpers/fixtures'
import { setupMswServer } from '../helpers/msw'
import { renderRoute } from '../helpers/render'

const ok = (data?: unknown) => HttpResponse.json({ code: 0, message: '', data })

setupMswServer(
  http.get('*/api/v1/tasks/data', () =>
    HttpResponse.json(
      makeTasksPageResponse([
        makeTaskDataRaw({ room_id: 23058 }, { running_status: 'recording' }),
        makeTaskDataRaw(
          { room_id: 100, user_name: '主播B', room_title: '房间B' },
          {
            running_status: 'stopped',
            monitor_enabled: false,
            recorder_enabled: false,
          },
        ),
      ]),
    ),
  ),
  http.get('*/api/v1/app/status', () =>
    ok({ started: true, task_count: 2, recording_count: 1 }),
  ),
  http.get('*/api/v1/tasks/:roomId/data', ({ params }) =>
    ok(makeTaskDataRaw({ room_id: Number(params.roomId) })),
  ),
  http.get('*/api/v1/tasks/:roomId/param', () => ok({ stream_format: 'flv' })),
  http.get('*/api/v1/tasks/:roomId/metadata', () => ok({ title: 'x' })),
  http.get('*/api/v1/tasks/:roomId/profile', () => ok({ quality: 10000 })),
  http.get('*/api/v1/tasks/:roomId/videos', () => ok({ videos: [] })),
  http.get('*/api/v1/tasks/:roomId/danmakus', () => ok({ danmakus: [] })),
  http.post('*/api/v1/tasks/:roomId/stop', () => ok()),
  http.post('*/api/v1/tasks/:roomId/start', () => ok()),
  http.post('*/api/v1/tasks/:roomId', () => ok({ room_id: 999 })),
)

describe('activeNavKey', () => {
  it('前缀匹配与缺省', () => {
    expect(activeNavKey('/tasks/23058')).toBe('/tasks')
    expect(activeNavKey('/settings')).toBe('/settings')
    expect(activeNavKey('/unknown')).toBe('/dashboard')
  })
})

describe('布局外壳 + 路由', () => {
  it('/ 重定向到 /dashboard 并渲染品牌与导航', async () => {
    const { router } = renderRoute(['/'])
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/dashboard'),
    )
    expect(screen.getByText('bili-rec')).toBeTruthy()
    expect(screen.getAllByText('概览').length).toBeGreaterThan(0)
  })

  it('顶栏「添加任务」跳转 /tasks/new', async () => {
    const { router } = renderRoute(['/dashboard'])
    fireEvent.click(screen.getByRole('button', { name: /添加任务/ }))
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/tasks/new'),
    )
  })

  it('点击侧栏「设置」导航到 /settings', async () => {
    const { router } = renderRoute(['/dashboard'])
    fireEvent.click(screen.getByText('设置'))
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/settings'),
    )
  })
})

describe('任务列表页', () => {
  it('渲染卡片网格与直播状态', async () => {
    renderRoute(['/tasks'])
    await waitFor(() =>
      expect(screen.getAllByTestId('task-card').length).toBe(2),
    )
    expect(screen.getByText('哔哩哔哩音悦台')).toBeTruthy()
    expect(screen.getAllByText('直播中').length).toBeGreaterThan(0)
  })

  it('录制中卡片带呼吸描边类名', async () => {
    renderRoute(['/tasks'])
    const cards = await screen.findAllByTestId('task-card')
    const recording = cards.find((c) => c.dataset.recording === 'true')
    expect(recording?.className).toContain('task-card--recording')
  })
})

describe('任务详情页', () => {
  it('渲染信息头与状态标签页', async () => {
    renderRoute(['/tasks/23058'])
    expect((await screen.findAllByText('录制中')).length).toBeGreaterThan(0)
    expect(screen.getByText('运行状态')).toBeTruthy()
    fireEvent.click(screen.getByRole('tab', { name: '参数' }))
    await waitFor(() => expect(screen.getByText('stream_format')).toBeTruthy())
  })

  it('无效房间号提示', () => {
    renderRoute(['/tasks/abc'])
    expect(screen.getByText('无效的房间号')).toBeTruthy()
  })
})

describe('添加任务页', () => {
  it('校验必填', async () => {
    renderRoute(['/tasks/new'])
    fireEvent.click(screen.getByRole('button', { name: /^添\s*加$/ }))
    expect(await screen.findByText('请输入房间号')).toBeTruthy()
  })

  it('填入房号提交后跳回列表', async () => {
    const { router } = renderRoute(['/tasks/new'])
    fireEvent.change(screen.getByPlaceholderText('例如 23058'), {
      target: { value: '23058' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^添\s*加$/ }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/tasks'))
  })
})

describe('Dashboard', () => {
  it('渲染统计卡片与录制中快捷卡片', async () => {
    renderRoute(['/dashboard'])
    await waitFor(() =>
      expect(screen.getAllByTestId('recording-quick-card').length).toBe(1),
    )
    expect(screen.getByText('总任务')).toBeTruthy()
  })
})

describe('占位页路由', () => {
  it('/about 渲染占位提示', async () => {
    const { router } = renderRoute(['/about'])
    await waitFor(() => expect(router.state.location.pathname).toBe('/about'))
    expect(screen.getAllByText('关于').length).toBeGreaterThan(0)
  })
})
