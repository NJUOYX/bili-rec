/**
 * TanStack Query 全局配置（frontend-design.md §6.1）。
 *
 * 重试策略：业务/404/403 错误不重试（重试无意义且拖慢反馈），
 * 仅网络类错误与未知异常做有限重试；动态数据的新鲜度主要靠
 * WS 事件驱动失效（FM2），staleTime 取保守小值以减少轮询。
 */
import { QueryClient } from '@tanstack/react-query'

import { ApiError } from '../api/client'

/** 最大重试次数（不含首个请求）。 */
export const MAX_RETRIES = 2

/** 查询重试判定：仅网络错误/未知异常重试，业务错误立即失败。 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.kind !== 'network') {
    return false
  }
  return failureCount < MAX_RETRIES
}

/** 创建应用级 QueryClient（工厂形式便于测试各自隔离实例）。 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 5000),
        staleTime: 5_000,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  })
}
