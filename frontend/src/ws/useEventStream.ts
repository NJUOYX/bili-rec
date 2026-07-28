/**
 * `/ws/v1/events` 订阅 hook（frontend-design.md §7.1-§7.4）。
 *
 * 挂载即建立连接（卸载关闭）：
 * - 连接状态写入 useConnectionStore（'events' 通道，供顶栏指示灯）；
 * - 业务事件入 useEventLogStore（Dashboard 时间线 / 事件面板）；
 * - 同步执行事件→缓存失效映射（applyEventToCache）；
 * - ping 仅由连接层判活（重置心跳），不入日志、不触发失效；
 * - 畸形载荷经解析守卫拒绝后静默丢弃。
 */
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { useConnectionStore } from '../stores/connection'
import { useEventLogStore } from '../stores/eventLog'
import { WsConnection, wsUrl, type WebSocketFactory } from './connection'
import { isPing, parseEventMessage } from './events'
import { applyEventToCache } from './invalidate'
import type { ReconnectPolicy } from './reconnect'

export interface EventStreamOptions {
  /** 覆盖 WS 地址（缺省同源 `/ws/v1/events`）。 */
  url?: string
  /** WebSocket 构造工厂（测试注入 mock）。 */
  factory?: WebSocketFactory
  /** 退避策略（测试注入零抖动）。 */
  policy?: ReconnectPolicy
}

export function useEventStream(options?: EventStreamOptions): void {
  const queryClient = useQueryClient()
  const url = options?.url
  const factory = options?.factory
  const policy = options?.policy

  useEffect(() => {
    const connection = new WsConnection({
      url: url ?? wsUrl('/ws/v1/events'),
      factory,
      policy,
      onStatusChange: (status) =>
        useConnectionStore.getState().setStatus('events', status),
      onMessage: (raw) => {
        const message = parseEventMessage(raw)
        if (message === null || isPing(message)) return
        useEventLogStore.getState().pushEvent(message)
        applyEventToCache(queryClient, message)
      },
    })
    connection.start()
    return () => connection.stop()
  }, [queryClient, url, factory, policy])
}
