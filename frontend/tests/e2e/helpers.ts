/**
 * E2E 测试夹具（frontend-design.md §10.2/§10.3）。
 *
 * - installApi：用 page.route 拦截同源 `/api/v1/**`，按方法+路径分发确定性
 *   响应（ResponseMessage 统一体）；支持覆盖任务列表与二维码轮询序列。
 * - installOpenWs：addInitScript 注入自动 open 的 WebSocket，使连接指示灯变绿；
 *   缺省（不注入）时 preview 无 WS 后端，指示灯保持非「已连接」。
 */
import type { Page, Route } from '@playwright/test'

import {
  makeTaskDataRaw,
  makeTasksPageResponse,
} from '../unit/helpers/fixtures'

type Json = Record<string, unknown>

const respond = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })

const ok = (data?: unknown) => ({ code: 0, message: '', data })

export interface ApiOptions {
  /** GET /tasks/data 返回的任务列表；缺省两条（录制中 + 已停止）。 */
  tasks?: Json[]
  /** POST /qrcode/login/poll 依次返回的业务码；末位之后重复末位。 */
  pollCodes?: number[]
}

const DEFAULT_TASKS: Json[] = [
  makeTaskDataRaw({ room_id: 23058 }, { running_status: 'recording' }),
  makeTaskDataRaw(
    { room_id: 100, user_name: '主播B', room_title: '房间B' },
    {
      running_status: 'stopped',
      monitor_enabled: false,
      recorder_enabled: false,
    },
  ),
]

/** 安装 REST 路由拦截（page.route 拦截同源 `/api/v1/**`）。 */
export async function installApi(
  page: Page,
  options: ApiOptions = {},
): Promise<void> {
  const tasks = options.tasks ?? DEFAULT_TASKS
  const pollCodes = options.pollCodes ?? [86101, 86090, 0]
  let pollIndex = 0

  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace(/^.*\/api\/v1/, '')
    const method = req.method()

    // 任务列表
    if (path === '/tasks/data' && method === 'GET') {
      return respond(route, makeTasksPageResponse(tasks))
    }
    // 二维码
    if (path === '/qrcode/login' && method === 'GET') {
      return respond(
        route,
        ok({ url: 'https://passport.bilibili.com/qr', auth_code: 'AUTH123' }),
      )
    }
    if (path === '/qrcode/login/poll' && method === 'POST') {
      const code = pollCodes[Math.min(pollIndex, pollCodes.length - 1)]
      pollIndex += 1
      return respond(route, { code, message: '', data: code === 0 ? {} : null })
    }
    // 应用状态/信息/版本
    if (path === '/app/status' && method === 'GET') {
      return respond(
        route,
        ok({
          started: true,
          task_count: tasks.length,
          recording_count: 1,
          disk_total: 1024 ** 3 * 100,
          disk_used: 1024 ** 3 * 40,
          disk_usage: 0.4,
        }),
      )
    }
    if (path === '/app/info' && method === 'GET') {
      return respond(
        route,
        ok({ name: 'bili-rec', version: '0.1.0', python: '3.12', pid: 1 }),
      )
    }
    if (path === '/update/version/latest' && method === 'GET') {
      return respond(route, ok({ version: '0.1.0', current: '0.1.0' }))
    }
    // 设置
    if (path === '/settings' && method === 'GET') {
      return respond(route, ok({ output: {}, recorder: {}, danmaku: {} }))
    }
    // 单任务子资源（GET）
    if (
      /^\/tasks\/\d+\/(param|metadata|profile|videos|danmakus|data)$/.test(path)
    ) {
      const leaf = path.split('/').pop()
      const map: Record<string, unknown> = {
        param: { stream_format: 'flv' },
        metadata: { title: 'x' },
        profile: { quality: 10000 },
        videos: { videos: [] },
        danmakus: { danmakus: [] },
        data: makeTaskDataRaw({ room_id: Number(path.split('/')[2]) }),
      }
      return respond(route, ok(map[leaf ?? 'data']))
    }
    // 其余（启停/录制器/info/删除/批量/校验/重启退出/PATCH 设置/新增任务）成功
    return respond(route, ok({ room_id: 999 }))
  })
}

/** 注入自动 open 的 WebSocket，使连接指示灯变为「已连接」。 */
export async function installOpenWs(page: Page): Promise<void> {
  await page.addInitScript(() => {
    class MockWebSocket {
      static readonly CONNECTING = 0
      static readonly OPEN = 1
      static readonly CLOSING = 2
      static readonly CLOSED = 3
      onopen: ((e: unknown) => void) | null = null
      onmessage: ((e: { data: unknown }) => void) | null = null
      onclose: ((e: unknown) => void) | null = null
      onerror: ((e: unknown) => void) | null = null
      readyState = 0
      url = ''
      constructor(url: string) {
        this.url = url
        setTimeout(() => {
          this.readyState = 1
          this.onopen?.({})
        }, 0)
      }
      send() {}
      close() {
        this.readyState = 3
        this.onclose?.({})
      }
    }
    // @ts-expect-error 覆盖全局 WebSocket 供 WsConnection 使用。
    window.WebSocket = MockWebSocket
  })
}

/** 注入永不 open 的 WebSocket（停在 CONNECTING），指示灯保持「重连中」。 */
export async function installStalledWs(page: Page): Promise<void> {
  await page.addInitScript(() => {
    class StalledWebSocket {
      static readonly CONNECTING = 0
      static readonly OPEN = 1
      static readonly CLOSING = 2
      static readonly CLOSED = 3
      onopen: ((e: unknown) => void) | null = null
      onmessage: ((e: { data: unknown }) => void) | null = null
      onclose: ((e: unknown) => void) | null = null
      onerror: ((e: unknown) => void) | null = null
      readyState = 0
      url = ''
      constructor(url: string) {
        this.url = url
      }
      send() {}
      close() {}
    }
    // @ts-expect-error 覆盖全局 WebSocket 供 WsConnection 使用。
    window.WebSocket = StalledWebSocket
  })
}
