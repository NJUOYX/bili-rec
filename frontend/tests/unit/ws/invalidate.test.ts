/**
 * 事件→缓存失效映射测试（frontend-design.md §7.4）。
 *
 * 对每类事件断言 invalidateQueries 收到的 queryKey 集合与设计表一致。
 */
import { QueryClient } from '@tanstack/react-query'

import { applyEventToCache } from '../../../src/ws/invalidate'
import type { AppEvent, FileEventType } from '../../../src/ws/events'

function makeFileEvent(type: FileEventType, roomId: number): AppEvent {
  return {
    type,
    id: 'id-1',
    date: '2026-07-28T12:00:00+08:00',
    data: { room_id: roomId, path: '/rec/a.flv' },
  }
}

function setup() {
  const queryClient = new QueryClient()
  const spy = vi.spyOn(queryClient, 'invalidateQueries')
  const invalidatedKeys = () => spy.mock.calls.map(([f]) => f?.queryKey)
  return { queryClient, spy, invalidatedKeys }
}

describe('applyEventToCache（§7.4 映射表）', () => {
  it.each(['VideoFileCreatedEvent', 'VideoFileCompletedEvent'] as const)(
    '%s → 失效 videos + data',
    (type) => {
      const { queryClient, invalidatedKeys } = setup()
      applyEventToCache(queryClient, makeFileEvent(type, 123))
      expect(invalidatedKeys()).toEqual([
        ['task', 123, 'videos'],
        ['task', 123, 'data'],
      ])
    },
  )

  it.each([
    'DanmakuFileCreatedEvent',
    'DanmakuFileCompletedEvent',
    'RawDanmakuFileCreatedEvent',
    'RawDanmakuFileCompletedEvent',
  ] as const)('%s → 失效 danmakus + data', (type) => {
    const { queryClient, invalidatedKeys } = setup()
    applyEventToCache(queryClient, makeFileEvent(type, 456))
    expect(invalidatedKeys()).toEqual([
      ['task', 456, 'danmakus'],
      ['task', 456, 'data'],
    ])
  })

  it('CoverImageDownloadedEvent → 失效任务列表前缀 + 详情 data（更新卡片封面）', () => {
    const { queryClient, invalidatedKeys } = setup()
    applyEventToCache(
      queryClient,
      makeFileEvent('CoverImageDownloadedEvent', 789),
    )
    expect(invalidatedKeys()).toEqual([['tasks'], ['task', 789, 'data']])
  })

  it('VideoPostprocessingCompletedEvent → 失效 data（后处理进度/产物）', () => {
    const { queryClient, invalidatedKeys } = setup()
    applyEventToCache(
      queryClient,
      makeFileEvent('VideoPostprocessingCompletedEvent', 11),
    )
    expect(invalidatedKeys()).toEqual([['task', 11, 'data']])
  })

  it('PostprocessingCompletedEvent → 失效 data', () => {
    const { queryClient, invalidatedKeys } = setup()
    applyEventToCache(queryClient, {
      type: 'PostprocessingCompletedEvent',
      id: 'id-2',
      date: '2026-07-28T12:00:00+08:00',
      data: { room_id: 22, files: ['/rec/a.mp4'] },
    })
    expect(invalidatedKeys()).toEqual([['task', 22, 'data']])
  })

  it('Error 事件无缓存动作（交由事件面板/toast，§9）', () => {
    const { queryClient, spy } = setup()
    applyEventToCache(queryClient, {
      type: 'Error',
      id: 'id-3',
      date: '2026-07-28T12:00:00+08:00',
      data: { name: 'RuntimeError', detail: 'boom' },
    })
    expect(spy).not.toHaveBeenCalled()
  })

  it('列表前缀失效可命中带参数的 tasks 缓存（前缀匹配语义）', async () => {
    const { queryClient } = setup()
    // 预置一条带参数的任务列表缓存
    queryClient.setQueryData(['tasks', { page: 1, size: 10 }], { total: 0 })
    applyEventToCache(
      queryClient,
      makeFileEvent('CoverImageDownloadedEvent', 1),
    )
    const state = queryClient.getQueryState(['tasks', { page: 1, size: 10 }])
    expect(state?.isInvalidated).toBe(true)
  })
})
