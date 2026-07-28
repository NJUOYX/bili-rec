/**
 * TanStack Query 测试辅助：隔离的 QueryClient + renderHook wrapper。
 * 测试内关闭重试，保证错误分支断言的确定性。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

/** 每个测试用独立 QueryClient，避免跨用例缓存串扰。 */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
}

/** renderHook 的 wrapper 工厂；可传入自建 client 以便断言缓存行为。 */
export function createQueryWrapper(
  client: QueryClient = createTestQueryClient(),
) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}
