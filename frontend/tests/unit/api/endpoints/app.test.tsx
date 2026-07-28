/**
 * M28 DT：应用域 hooks（MSW 契约 Mock，frontend-design.md §10.1）。
 */
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'

import { ApiError } from '../../../../src/api/client'
import { useAppInfo, useAppStatus } from '../../../../src/api/endpoints/app'
import { setupMswServer } from '../../helpers/msw'
import { createQueryWrapper } from '../../helpers/query'

const server = setupMswServer()

describe('useAppStatus', () => {
  it('成功：拆包返回应用状态', async () => {
    const status = { tasks: { total: 3, recording: 1 }, space: { free: 1024 } }
    server.use(
      http.get('/api/v1/app/status', () =>
        HttpResponse.json({ code: 0, message: '', data: status }),
      ),
    )
    const { result } = renderHook(() => useAppStatus(), {
      wrapper: createQueryWrapper(),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(status)
  })

  it('网络错误 → ApiError(kind=network)', async () => {
    server.use(http.get('/api/v1/app/status', () => HttpResponse.error()))
    const { result } = renderHook(() => useAppStatus(), {
      wrapper: createQueryWrapper(),
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect((result.current.error as ApiError).kind).toBe('network')
  })
})

describe('useAppInfo', () => {
  it('成功：拆包返回应用信息', async () => {
    const info = { name: 'birec', version: '0.1.0', pid: 42 }
    server.use(
      http.get('/api/v1/app/info', () =>
        HttpResponse.json({ code: 0, message: '', data: info }),
      ),
    )
    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createQueryWrapper(),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(info)
  })

  it('HTTP 503（Bili API 未初始化）统一体 → 业务 ApiError', async () => {
    server.use(
      http.get('/api/v1/app/info', () =>
        HttpResponse.json({ code: 503, message: 'Bili API not initialized' }),
      ),
    )
    const { result } = renderHook(() => useAppInfo(), {
      wrapper: createQueryWrapper(),
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    const error = result.current.error as ApiError
    expect(error.code).toBe(503)
    expect(error.kind).toBe('business')
  })
})
