/**
 * M33 DT：任务列表/详情/添加页交互全覆盖（§14.6）。
 *
 * 补齐 pages/tasks 的分支/操作回调覆盖：筛选切换、批量操作、卡片操作
 * （启停/录制器/更多菜单/删除确认）、详情页单任务操作与标签页、错误/空/
 * 不存在等降级态。MSW 依契约提供响应并以计数器断言 mutation 触发。
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import { formatTimestamp } from '../../../src/lib/format'
import { makeTaskDataRaw, makeTasksPageResponse } from '../helpers/fixtures'
import { setupMswServer } from '../helpers/msw'
import { renderRoute } from '../helpers/render'

const ok = (data?: unknown) => HttpResponse.json({ code: 0, message: '', data })

const calls: Record<string, number> = {}
/** 计数并返回成功响应的 MSW resolver（避免逗号表达式触发 no-sequences）。 */
const okHit = (key: string) => () => {
  calls[key] = (calls[key] ?? 0) + 1
  return ok()
}

let listSelect: string | null = null

const server = setupMswServer(
  http.get('*/api/v1/tasks/data', ({ request }) => {
    listSelect = new URL(request.url).searchParams.get('select')
    return HttpResponse.json(
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
    )
  }),
  // 单任务子资源
  http.get('*/api/v1/tasks/:roomId/data', ({ params }) =>
    ok(makeTaskDataRaw({ room_id: Number(params.roomId) })),
  ),
  http.get('*/api/v1/tasks/:roomId/param', () =>
    ok({ stream_format: 'flv', enable_monitor: true, enable_recorder: false }),
  ),
  http.get('*/api/v1/tasks/:roomId/metadata', () =>
    ok({ title: 'x', live_start_time: 1700000000, cover_url: '' }),
  ),
  http.get('*/api/v1/tasks/:roomId/profile', () => ok({ quality: 10000 })),
  http.get('*/api/v1/tasks/:roomId/videos', () =>
    ok({
      videos: [
        { path: '/rec/23058/a.flv', size: 2048, status: 'recording' },
        // 后端畸形条目应降级而非崩溃。
        { size: 'x' },
      ],
    }),
  ),
  http.get('*/api/v1/tasks/:roomId/danmakus', () =>
    ok({
      danmakus: [
        { path: '/rec/23058/a.xml', size: 207, status: 'recording' },
        { path: '/rec/23058/a.jsonl', size: 0, status: 'unknown' },
      ],
    }),
  ),
  // 单任务操作
  http.post('*/api/v1/tasks/:roomId/start', okHit('start')),
  http.post('*/api/v1/tasks/:roomId/stop', okHit('stop')),
  http.post('*/api/v1/tasks/:roomId/recorder/enable', okHit('recEnable')),
  http.post('*/api/v1/tasks/:roomId/recorder/disable', okHit('recDisable')),
  http.post('*/api/v1/tasks/:roomId/info', okHit('info')),
  http.delete('*/api/v1/tasks/:roomId', okHit('delete')),
  // 批量操作
  http.post('*/api/v1/tasks/start', okHit('batchStart')),
  http.post('*/api/v1/tasks/stop', okHit('batchStop')),
  http.post('*/api/v1/tasks/recorder/enable', okHit('batchRecEnable')),
  http.post('*/api/v1/tasks/info', okHit('batchInfo')),
)

beforeEach(() => {
  for (const k of Object.keys(calls)) delete calls[k]
  listSelect = null
})

describe('任务列表页 · 筛选与批量', () => {
  it('切换筛选器改变 GET /tasks/data 的 select', async () => {
    renderRoute(['/tasks'])
    await screen.findAllByTestId('task-card')
    fireEvent.click(screen.getByText('等待开播'))
    await waitFor(() => expect(listSelect).toBe('waiting'))
  })

  it('批量操作按钮触发对应端点', async () => {
    renderRoute(['/tasks'])
    await screen.findAllByTestId('task-card')

    fireEvent.click(screen.getByRole('button', { name: /全部启动/ }))
    await waitFor(() => expect(calls.batchStart).toBe(1))

    fireEvent.click(screen.getByRole('button', { name: /全部停止/ }))
    await waitFor(() => expect(calls.batchStop).toBe(1))

    fireEvent.click(screen.getByRole('button', { name: /全部录制/ }))
    await waitFor(() => expect(calls.batchRecEnable).toBe(1))

    fireEvent.click(screen.getByRole('button', { name: /刷新信息/ }))
    await waitFor(() => expect(calls.batchInfo).toBe(1))
  })
})

describe('任务列表页 · 卡片操作', () => {
  it('切换录制器开关触发单任务录制器端点', async () => {
    renderRoute(['/tasks'])
    await screen.findAllByTestId('task-card')
    // 第一张卡（23058）录制器已开 → 关闭；第二张已关 → 开启。
    const switches = screen.getAllByLabelText('录制器开关')
    fireEvent.click(switches[0])
    await waitFor(() => expect(calls.recDisable).toBe(1))
    fireEvent.click(switches[1])
    await waitFor(() => expect(calls.recEnable).toBe(1))
  })

  it('更多菜单「刷新信息」与「删除任务」确认', async () => {
    renderRoute(['/tasks'])
    const cards = await screen.findAllByTestId('task-card')
    const more = within(cards[0]).getByLabelText('更多操作')

    fireEvent.mouseEnter(more)
    fireEvent.click(await screen.findByRole('menuitem', { name: /刷新信息/ }))
    await waitFor(() => expect(calls.info).toBe(1))

    fireEvent.mouseEnter(more)
    fireEvent.click(await screen.findByRole('menuitem', { name: /删除任务/ }))
    // 弹出确认框，点「删除」。
    const confirm = await screen.findByRole('button', { name: /^删\s*除$/ })
    fireEvent.click(confirm)
    await waitFor(() => expect(calls.delete).toBe(1))
  })
})

describe('任务列表页 · 降级态', () => {
  it('加载失败展示重试', async () => {
    server.use(
      http.get('*/api/v1/tasks/data', () =>
        HttpResponse.json({ code: 500, message: '服务器错误' }),
      ),
    )
    renderRoute(['/tasks'])
    expect(await screen.findByText('加载失败')).toBeTruthy()
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeTruthy()
  })

  it('空列表展示暂无任务', async () => {
    server.use(
      http.get('*/api/v1/tasks/data', () =>
        HttpResponse.json(makeTasksPageResponse([])),
      ),
    )
    renderRoute(['/tasks'])
    expect(await screen.findByText('暂无任务')).toBeTruthy()
  })
})

describe('任务详情页 · 操作与标签页', () => {
  it('停止/录制器/刷新触发单任务端点', async () => {
    renderRoute(['/tasks/23058'])
    await screen.findAllByText('录制中')

    fireEvent.click(screen.getByRole('button', { name: /停\s*止/ }))
    await waitFor(() => expect(calls.stop).toBe(1))

    fireEvent.click(screen.getByRole('button', { name: /刷新信息/ }))
    await waitFor(() => expect(calls.info).toBe(1))

    // 录制器已开 → 关闭。
    fireEvent.click(screen.getByRole('switch'))
    await waitFor(() => expect(calls.recDisable).toBe(1))
  })

  it('各标签页结构化展示子资源', async () => {
    renderRoute(['/tasks/23058'])
    await screen.findAllByText('录制中')

    // 元数据：未映射的字段回退原始键名作标签；时间戳/空值可读化。
    fireEvent.click(screen.getByRole('tab', { name: '元数据' }))
    expect(await screen.findByText('title')).toBeTruthy()
    expect(screen.getByText(formatTimestamp(1700000000))).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()

    // 参数：布尔值渲染为启用/停用。
    fireEvent.click(screen.getByRole('tab', { name: '参数' }))
    expect(await screen.findByText('已启用')).toBeTruthy()
    expect(screen.getByText('已停用')).toBeTruthy()

    // Profile 无固定字段，仍为 JSON 视图。
    fireEvent.click(screen.getByRole('tab', { name: 'Profile' }))
    await waitFor(() => {
      const views = screen.getAllByTestId('json-view')
      expect(views.some((v) => v.textContent?.includes('quality'))).toBe(true)
    })

    // 视频：文件名 + 可读体积 + 状态标签。
    fireEvent.click(screen.getByRole('tab', { name: '视频' }))
    expect(await screen.findByText('a.flv')).toBeTruthy()
    expect(screen.getByText('2.0 KB')).toBeTruthy()

    // 弹幕：.xml 与 .jsonl 两条均列出。
    fireEvent.click(screen.getByRole('tab', { name: '弹幕' }))
    expect(await screen.findByText('a.xml')).toBeTruthy()
    expect(screen.getByText('a.jsonl')).toBeTruthy()
    // 视频页签的畸形条目同样降级为「未知」，故此处可能有多处命中。
    expect(screen.getAllByText('未知').length).toBeGreaterThan(0)
  })

  it('未录制时文件明细展示空态', async () => {
    server.use(
      http.get('*/api/v1/tasks/:roomId/danmakus', () => ok({ danmakus: [] })),
      http.get('*/api/v1/tasks/:roomId/param', () => ok({})),
    )
    renderRoute(['/tasks/23058'])
    await screen.findAllByText('录制中')
    fireEvent.click(screen.getByRole('tab', { name: '弹幕' }))
    expect(await screen.findByText('未在录制，暂无弹幕文件')).toBeTruthy()
    // 空响应的键值页签同样需降级而非渲染空表。
    fireEvent.click(screen.getByRole('tab', { name: '参数' }))
    expect(await screen.findByText('暂无数据')).toBeTruthy()
  })

  it('未开播任务展示启动按钮', async () => {
    server.use(
      http.get('*/api/v1/tasks/:roomId/data', ({ params }) =>
        ok(
          makeTaskDataRaw(
            { room_id: Number(params.roomId) },
            { monitor_enabled: false, running_status: 'stopped' },
          ),
        ),
      ),
    )
    renderRoute(['/tasks/23058'])
    const startBtn = await screen.findByRole('button', { name: /启\s*动/ })
    fireEvent.click(startBtn)
    await waitFor(() => expect(calls.start).toBe(1))
  })

  it('任务不存在展示返回列表', async () => {
    server.use(http.get('*/api/v1/tasks/:roomId/data', () => ok(null)))
    const { router } = renderRoute(['/tasks/999'])
    expect(await screen.findByText('任务不存在或加载失败')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /返回列表/ }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/tasks'))
  })
})

describe('添加任务页 · 取消', () => {
  it('点击取消返回列表', async () => {
    const { router } = renderRoute(['/tasks/new'])
    fireEvent.click(screen.getByRole('button', { name: /取\s*消/ }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/tasks'))
  })
})
