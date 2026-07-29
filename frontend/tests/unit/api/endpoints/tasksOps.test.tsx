/**
 * M30 DT：任务域操作/详情 hooks（MSW 契约 Mock，frontend-design.md §10.1）。
 * 覆盖：子资源路径替换、mutation 请求体、成功后缓存失效、业务错误分支。
 */
import { QueryClient } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'

import { ApiError } from '../../../../src/api/client'
import {
  useAddTask,
  useBatchRefreshInfo,
  useBatchSetRecorder,
  useBatchStart,
  useBatchStop,
  useDeleteTask,
  useDeleteTasks,
  useRefreshTaskInfo,
  useSetTaskRecorder,
  useStartTask,
  useStopTask,
  useTaskDanmakus,
  useTaskData,
  useTaskMetadata,
  useTaskParam,
  useTaskProfile,
  useTaskVideos,
} from '../../../../src/api/endpoints/tasks'
import { setupMswServer } from '../../helpers/msw'
import { createQueryWrapper, createTestQueryClient } from '../../helpers/query'

const server = setupMswServer()

const ok = (data?: Record<string, unknown>) =>
  HttpResponse.json({ code: 0, message: '', data })

describe('单任务子资源查询（GET /tasks/{room_id}/*）', () => {
  it.each([
    ['data', useTaskData, { room_id: 23058, live_status: true }],
    ['param', useTaskParam, { room_id: 23058, stream_format: 'flv' }],
    ['metadata', useTaskMetadata, { room_id: 23058, user_name: 'x' }],
    ['profile', useTaskProfile, { format: {} }],
    ['videos', useTaskVideos, { videos: [] }],
    ['danmakus', useTaskDanmakus, { danmakus: [] }],
  ] as const)(
    '%s：路径替换 room_id 并拆包 data',
    async (part, useHook, payload) => {
      let seenPath = ''
      server.use(
        http.get(`/api/v1/tasks/:roomId/${part}`, ({ request }) => {
          seenPath = new URL(request.url).pathname
          return ok(payload as Record<string, unknown>)
        }),
      )
      const { result } = renderHook(
        () => useHook(23058, { refetchInterval: false }),
        { wrapper: createQueryWrapper() },
      )
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(seenPath).toBe(`/api/v1/tasks/23058/${part}`)
      expect(result.current.data).toEqual(payload)
    },
  )

  it('404 任务不存在 → ApiError(not_found)', async () => {
    server.use(
      http.get('/api/v1/tasks/:roomId/data', () =>
        HttpResponse.json({ code: 404, message: 'Task 1 not found' }),
      ),
    )
    const { result } = renderHook(
      () => useTaskData(1, { refetchInterval: false }),
      { wrapper: createQueryWrapper() },
    )
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect((result.current.error as ApiError).kind).toBe('not_found')
  })
})

/** 断言 mutation 成功后按预期失效缓存键。 */
function spyInvalidate(client: QueryClient) {
  return vi.spyOn(client, 'invalidateQueries')
}

describe('单任务操作 mutations', () => {
  it('useAddTask：POST /tasks/{room_id} 携带 body 并失效列表', async () => {
    let seenBody: unknown
    let seenPath = ''
    server.use(
      http.post('/api/v1/tasks/:roomId', async ({ request }) => {
        seenPath = new URL(request.url).pathname
        seenBody = await request.json()
        return ok({ room_id: 23058 })
      }),
    )
    const client = createTestQueryClient()
    const invalidated = spyInvalidate(client)
    const { result } = renderHook(() => useAddTask(), {
      wrapper: createQueryWrapper(client),
    })
    await act(() => result.current.mutateAsync(23058))
    expect(seenPath).toBe('/api/v1/tasks/23058')
    expect(seenBody).toEqual({ room_id: 23058, auto_enable: true, save: false })
    expect(invalidated).toHaveBeenCalledWith({ queryKey: ['tasks'] })
  })

  it.each([
    ['start', useStartTask],
    ['stop', useStopTask],
    ['info', useRefreshTaskInfo],
  ] as const)(
    'POST /tasks/{room_id}/%s 并失效列表+单任务',
    async (action, useHook) => {
      let seenPath = ''
      server.use(
        http.post(`/api/v1/tasks/:roomId/${action}`, ({ request }) => {
          seenPath = new URL(request.url).pathname
          return ok()
        }),
      )
      const client = createTestQueryClient()
      const invalidated = spyInvalidate(client)
      const { result } = renderHook(() => useHook(), {
        wrapper: createQueryWrapper(client),
      })
      await act(() => result.current.mutateAsync(23058))
      expect(seenPath).toBe(`/api/v1/tasks/23058/${action}`)
      expect(invalidated).toHaveBeenCalledWith({ queryKey: ['tasks'] })
      expect(invalidated).toHaveBeenCalledWith({ queryKey: ['task', 23058] })
    },
  )

  it.each([
    [true, 'enable'],
    [false, 'disable'],
  ] as const)(
    'useSetTaskRecorder(enabled=%s) → recorder/%s',
    async (enabled, action) => {
      let seenPath = ''
      server.use(
        http.post(`/api/v1/tasks/:roomId/recorder/${action}`, ({ request }) => {
          seenPath = new URL(request.url).pathname
          return ok()
        }),
      )
      const { result } = renderHook(() => useSetTaskRecorder(), {
        wrapper: createQueryWrapper(),
      })
      await act(() => result.current.mutateAsync({ roomId: 23058, enabled }))
      expect(seenPath).toBe(`/api/v1/tasks/23058/recorder/${action}`)
    },
  )

  it('useDeleteTask：DELETE /tasks/{room_id}', async () => {
    let seenPath = ''
    server.use(
      http.delete('/api/v1/tasks/:roomId', ({ request }) => {
        seenPath = new URL(request.url).pathname
        return ok()
      }),
    )
    const { result } = renderHook(() => useDeleteTask(), {
      wrapper: createQueryWrapper(),
    })
    await act(() => result.current.mutateAsync(23058))
    expect(seenPath).toBe('/api/v1/tasks/23058')
  })

  it('业务错误（409 已存在）→ mutateAsync 拒绝并携带 ApiError', async () => {
    server.use(
      http.post('/api/v1/tasks/:roomId', () =>
        HttpResponse.json({ code: 409, message: 'Task already exists' }),
      ),
    )
    const { result } = renderHook(() => useAddTask(), {
      wrapper: createQueryWrapper(),
    })
    act(() => result.current.mutate(23058))
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toMatchObject({ code: 409, kind: 'business' })
  })
})

describe('批量操作 mutations', () => {
  it.each([
    ['start', useBatchStart],
    ['stop', useBatchStop],
  ] as const)('POST /tasks/%s 携带 room_ids', async (action, useHook) => {
    let seenBody: unknown
    server.use(
      http.post(`/api/v1/tasks/${action}`, async ({ request }) => {
        seenBody = await request.json()
        return ok()
      }),
    )
    const client = createTestQueryClient()
    const invalidated = spyInvalidate(client)
    const { result } = renderHook(() => useHook(), {
      wrapper: createQueryWrapper(client),
    })
    await act(() => result.current.mutateAsync([1, 2]))
    expect(seenBody).toMatchObject({ room_ids: [1, 2] })
    expect(invalidated).toHaveBeenCalledWith({ queryKey: ['tasks'] })
  })

  it('缺省参数 → 空 room_ids（=全部任务）', async () => {
    let seenBody: unknown
    server.use(
      http.post('/api/v1/tasks/start', async ({ request }) => {
        seenBody = await request.json()
        return ok()
      }),
    )
    const { result } = renderHook(() => useBatchStart(), {
      wrapper: createQueryWrapper(),
    })
    await act(() => result.current.mutateAsync(undefined as never))
    expect(seenBody).toEqual({ room_ids: [] })
  })

  it.each([
    [true, 'enable'],
    [false, 'disable'],
  ] as const)(
    'useBatchSetRecorder(enabled=%s) → recorder/%s',
    async (enabled, action) => {
      let seenBody: unknown
      server.use(
        http.post(`/api/v1/tasks/recorder/${action}`, async ({ request }) => {
          seenBody = await request.json()
          return ok()
        }),
      )
      const { result } = renderHook(() => useBatchSetRecorder(), {
        wrapper: createQueryWrapper(),
      })
      await act(() => result.current.mutateAsync({ roomIds: [3], enabled }))
      expect(seenBody).toEqual({ room_ids: [3] })
    },
  )

  it('useDeleteTasks：DELETE /tasks 携带 room_ids', async () => {
    let seenBody: unknown
    server.use(
      http.delete('/api/v1/tasks', async ({ request }) => {
        seenBody = await request.json()
        return ok()
      }),
    )
    const { result } = renderHook(() => useDeleteTasks(), {
      wrapper: createQueryWrapper(),
    })
    await act(() => result.current.mutateAsync([1, 2, 3]))
    expect(seenBody).toEqual({ room_ids: [1, 2, 3] })
  })

  it('useBatchRefreshInfo：POST /tasks/info', async () => {
    let called = false
    server.use(
      http.post('/api/v1/tasks/info', () => {
        called = true
        return ok()
      }),
    )
    const { result } = renderHook(() => useBatchRefreshInfo(), {
      wrapper: createQueryWrapper(),
    })
    await act(() => result.current.mutateAsync())
    expect(called).toBe(true)
  })
})
