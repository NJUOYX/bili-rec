/**
 * 全局 Provider 组合（frontend-design.md §3/§9/§14.2/§14.3）。
 *
 * - QueryClientProvider（M28，§6.1）；
 * - Ant Design ConfigProvider：注入 §14.2 主题令牌，亮/暗双主题跟随
 *   Zustand 主题 store（§14.3），中文 locale；
 * - antd `App`：提供 notification/message 静态方法的上下文（§9）；
 * - ApiErrorNotifier：订阅 Query/Mutation 缓存错误并弹通知（§9）。
 */
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { App as AntdApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { useEffect, useState, type ReactNode } from 'react'

import { describeApiError } from '../lib/errors'
import {
  selectResolved,
  useThemeStore,
  watchSystemTheme,
} from '../stores/theme'
import { createQueryClient } from './queryClient'
import { buildThemeConfig } from './theme'

/** 订阅 Query/Mutation 缓存的错误事件并弹 notification（§9）。 */
function ApiErrorNotifier({ client }: { client: QueryClient }) {
  const { notification } = AntdApp.useApp()
  useEffect(() => {
    const notify = (error: unknown) => {
      const { message, description } = describeApiError(error)
      notification.error({ message, description })
    }
    const offMutation = client.getMutationCache().subscribe((event) => {
      if (event.type === 'updated' && event.action.type === 'error') {
        notify(event.action.error)
      }
    })
    const offQuery = client.getQueryCache().subscribe((event) => {
      if (event.type === 'updated' && event.action.type === 'error') {
        notify(event.action.error)
      }
    })
    return () => {
      offMutation()
      offQuery()
    }
  }, [client, notification])
  return null
}

interface AppProvidersProps {
  children: ReactNode
  /** 可注入 QueryClient（测试用）；缺省时惰性创建应用级实例。 */
  queryClient?: QueryClient
}

export function AppProviders({ children, queryClient }: AppProvidersProps) {
  // useState 惰性初始化保证实例在组件生命周期内稳定（含 StrictMode 双渲染）。
  const [client] = useState(() => queryClient ?? createQueryClient())
  const resolved = useThemeStore(selectResolved)

  // system 模式跟随系统主题实时切换（§14.3）。
  useEffect(() => watchSystemTheme(), [])

  return (
    <QueryClientProvider client={client}>
      <ConfigProvider locale={zhCN} theme={buildThemeConfig(resolved)}>
        <AntdApp>
          <ApiErrorNotifier client={client} />
          {children}
        </AntdApp>
      </ConfigProvider>
    </QueryClientProvider>
  )
}
