/**
 * M28 DT：设置域 hooks（MSW 契约 Mock，frontend-design.md §10.1）。
 * 覆盖读写成功 / 业务错误 / 缓存失效联动。
 */
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'

import { ApiError } from '../../../../src/api/client'
import {
  usePatchSettings,
  useSettings,
} from '../../../../src/api/endpoints/settings'
import { queryKeys } from '../../../../src/api/queryKeys'
import { setupMswServer } from '../../helpers/msw'
import { createQueryWrapper, createTestQueryClient } from '../../helpers/query'

const server = setupMswServer()

const settingsData = {
  danmaku: { recordGiftSend: false },
  recorder: { qualityNumber: 20000 },
}

describe('useSettings', () => {
  it('成功：拆包返回全局设置', async () => {
    server.use(
      http.get('/api/v1/settings', () =>
        HttpResponse.json({ code: 0, message: '', data: settingsData }),
      ),
    )
    const { result } = renderHook(() => useSettings(), {
      wrapper: createQueryWrapper(),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(settingsData)
  })

  it('code!=0（如 422 校验失败）→ 业务 ApiError', async () => {
    server.use(
      http.get('/api/v1/settings', () =>
        HttpResponse.json({ code: 422, message: 'Validation error' }),
      ),
    )
    const { result } = renderHook(() => useSettings(), {
      wrapper: createQueryWrapper(),
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    const error = result.current.error as ApiError
    expect(error.code).toBe(422)
    expect(error.kind).toBe('business')
  })
})

describe('usePatchSettings', () => {
  it('成功：JSON body 透传，返回更新后的设置并失效 [settings] 缓存', async () => {
    let seenBody: unknown
    server.use(
      http.patch('/api/v1/settings', async ({ request }) => {
        seenBody = await request.json()
        return HttpResponse.json({
          code: 0,
          message: 'Settings updated',
          data: settingsData,
        })
      }),
    )
    const client = createTestQueryClient()
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => usePatchSettings(), {
      wrapper: createQueryWrapper(client),
    })

    const patch = { danmaku: { recordGiftSend: true } }
    result.current.mutate(patch)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(seenBody).toEqual(patch)
    expect(result.current.data).toEqual(settingsData)
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.settings(),
    })
  })

  it('code!=0 → mutation 失败且不触发缓存失效', async () => {
    server.use(
      http.patch('/api/v1/settings', () =>
        HttpResponse.json({
          code: 422,
          message: 'Validation error: 1 field(s)',
        }),
      ),
    )
    const client = createTestQueryClient()
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => usePatchSettings(), {
      wrapper: createQueryWrapper(client),
    })

    result.current.mutate({ recorder: { qualityNumber: -1 } })

    await waitFor(() => expect(result.current.isError).toBe(true))
    const error = result.current.error as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe(422)
    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})
