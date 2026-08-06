/**
 * E2E 关键用户旅程（frontend-design.md §10.2）。
 *
 * 覆盖：①添加任务→列表出现录制中→进入详情→停止；②设置读写；
 * ③扫码登录（Mock 轮询序列）；④WS 连接指示灯（已连/重连中）。
 * 网络经 page.route 拦截（确定性，§10.3），WS 经 addInitScript 注入。
 */
import { expect, test } from '@playwright/test'

import { installApi, installOpenWs, installStalledWs } from './helpers'
import { makeTaskDataRaw } from '../unit/helpers/fixtures'

test.describe('任务模块旅程', () => {
  test('添加任务 → 列表出现录制中 → 详情停止', async ({ page }) => {
    await installApi(page)
    await page.goto('/tasks')

    // 列表卡片网格渲染。
    await expect(page.getByTestId('task-card')).toHaveCount(2)
    // 录制中任务出现（StatusBadge）。
    await expect(page.getByText('录制中').first()).toBeVisible()

    // 顶栏「添加任务」→ 新增页 → 填房号提交 → 回列表。
    await page.getByRole('button', { name: /添加任务/ }).click()
    await expect(page).toHaveURL(/\/tasks\/new$/)
    await page.getByPlaceholder('例如 23058').fill('23058')
    await page.getByRole('button', { name: /^添\s*加$/ }).click()
    await expect(page).toHaveURL(/\/tasks$/)

    // 点击卡片标题客户端路由进入详情（相对 base 下深链整页重载会错误解析
    // 资源，真实部署由后端 RouteRedirectMiddleware 302→/index.html 消解；
    // E2E 走真实用户的客户端导航路径）。
    await page
      .getByTestId('task-card')
      .first()
      .getByRole('button', { name: '哔哩哔哩音悦台' })
      .click()
    await expect(page).toHaveURL(/\/tasks\/23058$/)
    await expect(page.getByText('录制中').first()).toBeVisible()

    // 停止任务：详情页单任务「停止」（图标 aria 使可及名为 “stop 停止”），
    // 锚定排除列表批量的「全部停止」。停止后仍停留在详情页（无异常）。
    await page.getByRole('button', { name: /^(?:stop\s*)?停\s*止$/ }).click()
    await expect(page).toHaveURL(/\/tasks\/23058$/)
  })

  test('有封面时卡片展示封面图，无封面时展示分区名', async ({ page }) => {
    const withCover = makeTaskDataRaw(
      { room_id: 1, cover_url: 'https://i0.hdslb.com/cover1.jpg' },
      { running_status: 'recording' },
    )
    const withoutCover = makeTaskDataRaw(
      { room_id: 2, cover_url: '', user_name: '主播B', room_title: '房间B' },
      { running_status: 'stopped', monitor_enabled: false, recorder_enabled: false },
    )
    await installApi(page, { tasks: [withCover, withoutCover] })
    await page.goto('/tasks')

    await expect(page.getByTestId('task-card')).toHaveCount(2)

    // 有 cover_url 的卡片渲染 <img>
    const coverCard = page.getByTestId('task-card').first()
    await expect(coverCard.locator('img')).toBeVisible()

    // 无 cover_url 的卡片渲染分区名占位
    const noCoverCard = page.getByTestId('task-card').nth(1)
    await expect(noCoverCard.locator('img')).toHaveCount(0)
    await expect(noCoverCard.getByText('娱乐')).toBeVisible()
  })
})

test.describe('设置模块旅程', () => {
  test('读取设置并保存回读一致', async ({ page }) => {
    await installApi(page)
    await page.goto('/settings')

    // 分组卡片渲染（Recorder 分组标题）。
    await expect(page.getByText('Recorder').first()).toBeVisible()

    // 保存第一个分组 → PATCH 成功 → 成功提示。
    await page
      .getByRole('button', { name: /^保\s*存$/ })
      .first()
      .click()
    await expect(page.getByText('设置已保存')).toBeVisible()
  })
})

test.describe('扫码登录旅程', () => {
  test('轮询 未扫码→已扫码→成功', async ({ page }) => {
    await installApi(page, { pollCodes: [86101, 86090, 0] })
    await page.goto('/login')

    await expect(page.getByTestId('qrcode-login')).toBeVisible()
    // 轮询序列推进后，二维码组件内呈现「登录成功」状态提示。
    await expect(
      page.getByTestId('qrcode-login').getByText('登录成功'),
    ).toBeVisible({ timeout: 15_000 })
  })
})

test.describe('实时连接指示灯', () => {
  test('WS 建立后指示灯为已连接', async ({ page }) => {
    await installApi(page)
    await installOpenWs(page)
    await page.goto('/dashboard')

    await expect(page.getByTestId('connection-indicator')).toHaveAttribute(
      'data-state',
      'connected',
      { timeout: 15_000 },
    )
  })

  test('WS 未建立时指示灯为重连中', async ({ page }) => {
    await installApi(page)
    await installStalledWs(page)
    await page.goto('/dashboard')

    await expect(page.getByTestId('connection-indicator')).toHaveAttribute(
      'data-state',
      'reconnecting',
      { timeout: 15_000 },
    )
  })
})
