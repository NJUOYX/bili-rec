/**
 * M28 DT：QueryClient 全局配置与重试策略（frontend-design.md §6.1）。
 */
import { ApiError } from '../../../src/api/client'
import {
  MAX_RETRIES,
  createQueryClient,
  shouldRetry,
} from '../../../src/app/queryClient'

describe('shouldRetry', () => {
  it('业务/404/403 错误不重试', () => {
    expect(shouldRetry(0, new ApiError(409, 'conflict'))).toBe(false)
    expect(shouldRetry(0, new ApiError(404, 'not found'))).toBe(false)
    expect(shouldRetry(0, new ApiError(403, 'forbidden'))).toBe(false)
  })

  it('网络错误重试至上限', () => {
    const err = new ApiError(-1, 'fetch failed', 'network')
    expect(shouldRetry(0, err)).toBe(true)
    expect(shouldRetry(MAX_RETRIES - 1, err)).toBe(true)
    expect(shouldRetry(MAX_RETRIES, err)).toBe(false)
  })

  it('未知异常按次数上限重试', () => {
    const err = new Error('boom')
    expect(shouldRetry(0, err)).toBe(true)
    expect(shouldRetry(MAX_RETRIES, err)).toBe(false)
  })
})

describe('createQueryClient', () => {
  it('注入重试策略与查询默认项', () => {
    const client = createQueryClient()
    const defaults = client.getDefaultOptions()
    expect(defaults.queries?.retry).toBe(shouldRetry)
    expect(defaults.queries?.staleTime).toBe(5_000)
    expect(defaults.queries?.refetchOnWindowFocus).toBe(false)
    expect(defaults.mutations?.retry).toBe(false)
  })

  it('重试退避指数增长且封顶 5s', () => {
    const client = createQueryClient()
    const retryDelay = client.getDefaultOptions().queries?.retryDelay as (
      attempt: number,
    ) => number
    expect(retryDelay(0)).toBe(1000)
    expect(retryDelay(1)).toBe(2000)
    expect(retryDelay(10)).toBe(5000)
  })
})
