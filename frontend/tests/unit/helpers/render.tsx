/**
 * 页面级渲染辅助：用内存路由装配真实 routes + 应用 Provider（QueryClient +
 * AntD ConfigProvider/App 上下文），供页面/布局集成测试使用。
 */
import { QueryClient } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'

import { AppProviders } from '../../../src/app/providers'
import { routes } from '../../../src/app/router'

/** 测试用 QueryClient：关闭重试与轮询，保证确定性。 */
export function createPageQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

/** 用内存路由渲染整个应用（含布局外壳），可指定初始路径。 */
export function renderRoute(
  initialEntries: string[] = ['/dashboard'],
  client: QueryClient = createPageQueryClient(),
) {
  const router = createMemoryRouter(routes, { initialEntries })
  const result = render(
    <AppProviders queryClient={client}>
      <RouterProvider router={router} />
    </AppProviders>,
  )
  return { ...result, router, client }
}
