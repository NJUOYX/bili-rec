/**
 * M28 DT：任务域 hooks（MSW 契约 Mock，frontend-design.md §10.1）。
 * 覆盖成功 / code!=0 业务错误 / 网络错误三分支与查询参数透传。
 */
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'

import { ApiError } from '../../../../src/api/client'
import { useTasksData } from '../../../../src/api/endpoints/tasks'
import { setupMswServer } from '../../helpers/msw'
import { createQueryWrapper } from '../../helpers/query'

const server = setupMswServer()

describe('useTasksData', () => {
  it('成功：拆包返回分页数据', async () => {
    const page = {
      total: 1,
      page: 1,
      size: 20,
      tasks: [{ room_id: 23058, live_status: true }],
    }
    server.use(
      http.get('/api/v1/tasks/data', () =>
        HttpResponse.json({ code: 0, message: '', data: page }),
      ),
    )
    const { result } = renderHook(() => useTasksData(), {
      wrapper: createQueryWrapper(),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(page)
  })

  it('查询参数（page/size/select）透传到请求 URL', async () => {
    let seenUrl: URL | undefined
    server.use(
      http.get('/api/v1/tasks/data', ({ request }) => {
        seenUrl = new URL(request.url)
        return HttpResponse.json({
          code: 0,
          message: '',
          data: { total: 0, page: 2, size: 10, tasks: [] },
        })
      }),
    )
    const { result } = renderHook(
      () => useTasksData({ page: 2, size: 10, select: 'recording' }),
      { wrapper: createQueryWrapper() },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(seenUrl?.searchParams.get('page')).toBe('2')
    expect(seenUrl?.searchParams.get('size')).toBe('10')
    expect(seenUrl?.searchParams.get('select')).toBe('recording')
  })

  it('code!=0 → 查询失败并暴露业务 ApiError', async () => {
    server.use(
      http.get('/api/v1/tasks/data', () =>
        HttpResponse.json({ code: 500, message: 'internal error' }),
      ),
    )
    const { result } = renderHook(() => useTasksData(), {
      wrapper: createQueryWrapper(),
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    const error = result.current.error as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe(500)
    expect(error.kind).toBe('business')
    expect(error.message).toBe('internal error')
  })

  it('网络错误 → ApiError(kind=network)', async () => {
    server.use(http.get('/api/v1/tasks/data', () => HttpResponse.error()))
    const { result } = renderHook(() => useTasksData(), {
      wrapper: createQueryWrapper(),
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect((result.current.error as ApiError).kind).toBe('network')
  })
})
