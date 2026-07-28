/**
 * 全局 Provider 组合（frontend-design.md §3）。
 *
 * M28 引入 QueryClientProvider；Ant Design ConfigProvider 与主题令牌
 * （§14.2 `app/theme.ts`）将随 M30 任务模块引入 UI 时组合于此。
 */
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'

import { createQueryClient } from './queryClient'

interface AppProvidersProps {
  children: ReactNode
  /** 可注入 QueryClient（测试用）；缺省时惰性创建应用级实例。 */
  queryClient?: QueryClient
}

export function AppProviders({ children, queryClient }: AppProvidersProps) {
  // useState 惰性初始化保证实例在组件生命周期内稳定（含 StrictMode 双渲染）。
  const [client] = useState(() => queryClient ?? createQueryClient())
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
