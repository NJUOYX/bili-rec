/**
 * `/ws/v1/exceptions` 订阅 hook（frontend-design.md §7.1/§9）。
 *
 * 挂载即建立连接（卸载关闭）：
 * - 连接状态写入 useConnectionStore（'exceptions' 通道）；
 * - 异常消息 `{type, message, traceback}` 入 useEventLogStore，
 *   供全局异常面板（traceback 折叠展示，M30+）消费；
 * - ping 仅判活；畸形载荷静默丢弃。
 */
import { useEffect } from 'react'

import { useConnectionStore } from '../stores/connection'
import { useEventLogStore } from '../stores/eventLog'
import { WsConnection, wsUrl, type WebSocketFactory } from './connection'
import { isPing, parseExceptionMessage } from './events'
import type { ReconnectPolicy } from './reconnect'

export interface ExceptionStreamOptions {
  /** 覆盖 WS 地址（缺省同源 `/ws/v1/exceptions`）。 */
  url?: string
  /** WebSocket 构造工厂（测试注入 mock）。 */
  factory?: WebSocketFactory
  /** 退避策略（测试注入零抖动）。 */
  policy?: ReconnectPolicy
}

export function useExceptionStream(options?: ExceptionStreamOptions): void {
  const url = options?.url
  const factory = options?.factory
  const policy = options?.policy

  useEffect(() => {
    const connection = new WsConnection({
      url: url ?? wsUrl('/ws/v1/exceptions'),
      factory,
      policy,
      onStatusChange: (status) =>
        useConnectionStore.getState().setStatus('exceptions', status),
      onMessage: (raw) => {
        const message = parseExceptionMessage(raw)
        if (message === null || isPing(message)) return
        useEventLogStore.getState().pushException(message)
      },
    })
    connection.start()
    return () => connection.stop()
  }, [url, factory, policy])
}
