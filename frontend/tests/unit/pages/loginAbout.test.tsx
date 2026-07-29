/**
 * M32 DT：登录页扫码轮询流 + 关于页信息/校验/进程操作（§8）。
 * 内存路由装配真实 routes，MSW 依契约提供响应。
 */
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { setupMswServer } from '../helpers/msw'
import { renderRoute } from '../helpers/render'

const ok = (data?: unknown) => HttpResponse.json({ code: 0, message: '', data })
const biz = (code: number, message: string) =>
  HttpResponse.json({ code, message })

// 轮询序列：首次「已扫码」，随后「成功」。
let pollCount = 0

const appInfo = {
  name: 'bili-rec',
  version: '0.1.0',
  python: '3.12.0',
  pid: 4242,
}
const appStatus = { started: true, task_count: 3, recording_count: 1 }

let validatedPath: string | null = null
let restartCalled = false
let exitCalled = false

setupMswServer(
  http.get('*/api/v1/qrcode/login', () =>
    ok({ url: 'https://qr.bilibili/abc', auth_code: 'AUTH123' }),
  ),
  http.post('*/api/v1/qrcode/login/poll', () => {
    pollCount += 1
    if (pollCount >= 2) return ok({ access_token: 't', cookie: 'c' })
    return biz(86090, '已扫码')
  }),
  http.get('*/api/v1/app/info', () => ok(appInfo)),
  http.get('*/api/v1/app/status', () => ok(appStatus)),
  http.get('*/api/v1/update/version/latest', () =>
    ok({ version: '0.1.0', current: '0.1.0' }),
  ),
  http.post('*/api/v1/validation/dir', async ({ request }) => {
    const body = (await request.json()) as { path: string }
    validatedPath = body.path
    return ok({ path: body.path })
  }),
  http.post('*/api/v1/app/restart', () => {
    restartCalled = true
    return ok()
  }),
  http.post('*/api/v1/app/exit', () => {
    exitCalled = true
    return ok()
  }),
)

describe('LoginPage', () => {
  it('渲染二维码并驱动轮询至登录成功', async () => {
    pollCount = 0
    renderRoute(['/login'])

    // 初始请求二维码后进入等待/已扫码状态。
    expect(await screen.findByTestId('qrcode-login')).toBeTruthy()
    expect(screen.getByText('扫码登录')).toBeTruthy()

    // 轮询（2s 间隔）推进到成功态。
    await waitFor(() => expect(screen.getByText('登录成功')).toBeTruthy(), {
      timeout: 8000,
    })
  })
})

describe('AboutPage', () => {
  it('展示应用信息与运行状态', async () => {
    validatedPath = null
    renderRoute(['/about'])

    expect(await screen.findByText('bili-rec')).toBeTruthy()
    expect(await screen.findByText('任务总数')).toBeTruthy()
    expect(await screen.findByText('已启动')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('已是最新版本')).toBeTruthy())
  })

  it('目录校验触发 POST /validation/dir', async () => {
    validatedPath = null
    renderRoute(['/about'])
    await screen.findByText('bili-rec')

    const input = screen.getByLabelText('目录路径')
    fireEvent.change(input, { target: { value: '/data/rec' } })
    fireEvent.click(screen.getByRole('button', { name: /校\s*验/ }))

    await waitFor(() => expect(validatedPath).toBe('/data/rec'))
  })

  it('重启需二次确认后触发 POST /app/restart', async () => {
    restartCalled = false
    renderRoute(['/about'])
    await screen.findByText('bili-rec')

    fireEvent.click(screen.getByRole('button', { name: /重启应用/ }))
    // Popconfirm 弹出确认按钮。
    const confirm = await screen.findByRole('button', { name: /^重\s*启$/ })
    fireEvent.click(confirm)

    await waitFor(() => expect(restartCalled).toBe(true))
  })

  it('退出需二次确认后触发 POST /app/exit', async () => {
    exitCalled = false
    renderRoute(['/about'])
    await screen.findByText('bili-rec')

    fireEvent.click(screen.getByRole('button', { name: /退出应用/ }))
    const confirm = await screen.findByRole('button', { name: /^退\s*出$/ })
    fireEvent.click(confirm)

    await waitFor(() => expect(exitCalled).toBe(true))
  })
})
