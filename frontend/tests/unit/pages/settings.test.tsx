/**
 * M31 DT：设置页与任务级设置页（§8.1）。
 * 用内存路由装配真实 routes，MSW 依契约提供 settings 响应。
 * 注：分组标题同时出现在锚点与卡片，用 id 定位卡片；AntD 双字按钮含空格。
 * 8 分组表单在 CI 渲染较慢，waitFor 放宽超时。
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { setupMswServer } from '../helpers/msw'
import { renderRoute } from '../helpers/render'

const ok = (data?: unknown) => HttpResponse.json({ code: 0, message: '', data })

const globalSettings = {
  biliApi: { baseApiUrls: ['https://api.bilibili.com'] },
  header: { userAgent: 'UA', cookie: '' },
  danmaku: { danmuUname: false, recordGiftSend: true },
  recorder: { streamFormat: 'flv', qualityNumber: 10000 },
  output: { outDir: '.', pathTemplate: '{roomid}' },
  postprocessing: { remuxToMp4: true, assFontSize: 38 },
  logging: { logDir: '/logs', consoleLogLevel: 'INFO', backupCount: 30 },
  space: {
    checkInterval: 60,
    spaceThreshold: 1073741824,
    recycleRecords: false,
  },
}

let lastPatch: unknown = null

const server = setupMswServer(
  http.get('*/api/v1/settings', () => ok(globalSettings)),
  http.patch('*/api/v1/settings', async ({ request }) => {
    lastPatch = await request.json()
    return ok(globalSettings)
  }),
  http.get('*/api/v1/settings/tasks/:roomId', () =>
    ok({ recorder: { streamFormat: null }, header: { userAgent: null } }),
  ),
  http.patch('*/api/v1/settings/tasks/:roomId', async ({ request }) => {
    lastPatch = await request.json()
    return ok({})
  }),
)

const WAIT = { timeout: 10000 }

function cardById(id: string): HTMLElement {
  const el = document.getElementById(id)
  if (!el) throw new Error(`card ${id} not found`)
  return el
}

async function saveGroup(id: string) {
  await waitFor(() => expect(document.getElementById(id)).toBeTruthy(), WAIT)
  fireEvent.click(within(cardById(id)).getByRole('button', { name: /保\s*存/ }))
}

describe('全局设置页', () => {
  it('渲染各分组表单卡片', async () => {
    renderRoute(['/settings'])
    await waitFor(
      () => expect(document.getElementById('settings-biliApi')).toBeTruthy(),
      WAIT,
    )
    expect(document.getElementById('settings-recorder')).toBeTruthy()
    expect(document.getElementById('settings-space')).toBeTruthy()
    expect(screen.getAllByText('Postprocessing').length).toBeGreaterThan(0)
  })

  it('保存分组触发 PATCH（body 为 { group: values }）', async () => {
    lastPatch = null
    renderRoute(['/settings'])
    await saveGroup('settings-space')
    await waitFor(
      () => expect(lastPatch).toMatchObject({ space: expect.any(Object) }),
      WAIT,
    )
  })

  it('保存分组时仅该分组按钮进入 loading', async () => {
    // 各分组共用一个 mutation，故须验证 loading 不会蔓延到其他分组。
    server.use(
      http.patch('*/api/v1/settings', async () => {
        await delay(200)
        return ok(globalSettings)
      }),
    )
    renderRoute(['/settings'])
    await saveGroup('settings-space')
    const saveBtn = (id: string) =>
      within(cardById(id)).getByRole('button', { name: /保\s*存/ })
    await waitFor(
      () =>
        expect(saveBtn('settings-space').className).toContain(
          'ant-btn-loading',
        ),
      WAIT,
    )
    expect(saveBtn('settings-recorder').className).not.toContain(
      'ant-btn-loading',
    )
  })

  it('连点多组时各组 loading 互不影响且都能收尾', async () => {
    // 共用 mutation 下若只记住最后一组，先提交的那组会提前停止转圈；
    // 若依赖 mutate 级 onSettled，则有一组会永远停在 loading。
    server.use(
      http.patch('*/api/v1/settings', async () => {
        await delay(300)
        return ok(globalSettings)
      }),
    )
    renderRoute(['/settings'])
    await saveGroup('settings-space')
    await saveGroup('settings-recorder')
    const saveBtn = (id: string) =>
      within(cardById(id)).getByRole('button', { name: /保\s*存/ })
    await waitFor(
      () =>
        expect(saveBtn('settings-recorder').className).toContain(
          'ant-btn-loading',
        ),
      WAIT,
    )
    expect(saveBtn('settings-space').className).toContain('ant-btn-loading')
    await waitFor(() => {
      expect(saveBtn('settings-space').className).not.toContain(
        'ant-btn-loading',
      )
      expect(saveBtn('settings-recorder').className).not.toContain(
        'ant-btn-loading',
      )
    }, WAIT)
  })
})

describe('任务级设置页', () => {
  it('渲染标题与可覆盖分组（不含 biliApi/space）', async () => {
    renderRoute(['/settings/tasks/23058'])
    await waitFor(
      () => expect(screen.getByText('房间 23058 的设置')).toBeTruthy(),
      WAIT,
    )
    expect(document.getElementById('settings-recorder')).toBeTruthy()
    expect(document.getElementById('settings-biliApi')).toBeNull()
    expect(document.getElementById('settings-space')).toBeNull()
  })

  it('无效房号提示', () => {
    renderRoute(['/settings/tasks/abc'])
    expect(screen.getByText('无效的房间号')).toBeTruthy()
  })

  it('保存任务分组触发任务级 PATCH', async () => {
    lastPatch = null
    renderRoute(['/settings/tasks/23058'])
    await saveGroup('settings-header')
    await waitFor(
      () => expect(lastPatch).toMatchObject({ header: expect.any(Object) }),
      WAIT,
    )
  })

  it('枚举字段的继承提示用选项标签而非原始值', async () => {
    renderRoute(['/settings/tasks/23058'])
    await waitFor(
      () => expect(document.getElementById('settings-recorder')).toBeTruthy(),
      WAIT,
    )
    const card = cardById('settings-recorder')
    // 全局 streamFormat=flv / qualityNumber=10000 → “FLV” / “原画”。
    expect(within(card).getByText('FLV')).toBeTruthy()
    expect(within(card).getByText('原画')).toBeTruthy()
    expect(within(card).queryByText('10000')).toBeNull()
  })

  it('开关字段以文字说明继承值', async () => {
    renderRoute(['/settings/tasks/23058'])
    await waitFor(
      () => expect(document.getElementById('settings-danmaku')).toBeTruthy(),
      WAIT,
    )
    // 全局 recordGiftSend=true / danmuUname=false。
    const card = cardById('settings-danmaku')
    expect(within(card).getByText('继承全局：开')).toBeTruthy()
    expect(within(card).getByText('继承全局：关')).toBeTruthy()
  })
})
