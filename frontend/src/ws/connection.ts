/**
 * WebSocket 单连接管理器（frontend-design.md §7.3）。
 *
 * 职责：
 * - 生命周期：start/stop，状态机 connecting → open → reconnecting → closed；
 * - 心跳：>heartbeatTimeoutMs（默认 45s）未收到任何消息（含 ping）则判定
 *   假死，主动断开触发重连；
 * - 重连：意外断开后按指数退避（reconnect.ts）自动重建，成功后计数重置；
 * - 分发：JSON 帧解析后原样交给 onMessage（ping 过滤等语义由上层处理），
 *   非 JSON 帧静默丢弃。
 *
 * WebSocket 构造可注入（factory）以便测试与环境隔离；error 事件不独立
 * 触发重连——浏览器语义下 error 后必随 close，统一走 close 路径避免双重重连。
 */
import {
  backoffDelay,
  DEFAULT_RECONNECT_POLICY,
  HEARTBEAT_TIMEOUT_MS,
  type ReconnectPolicy,
} from './reconnect'

/** 连接状态（§6.2）。 */
export type ConnectionStatus = 'connecting' | 'open' | 'reconnecting' | 'closed'

/** WsConnection 依赖的最小 WebSocket 接口（便于注入 mock）。 */
export interface WebSocketLike {
  onopen: ((event: unknown) => void) | null
  onmessage: ((event: { data: unknown }) => void) | null
  onclose: ((event: unknown) => void) | null
  onerror: ((event: unknown) => void) | null
  close(): void
}

export type WebSocketFactory = (url: string) => WebSocketLike

export interface WsConnectionOptions {
  /** 完整 WS 地址（经 wsUrl 从页面源派生）。 */
  url: string
  /** 每条成功解析的 JSON 消息（含 ping）都会分发到此回调。 */
  onMessage: (raw: unknown) => void
  /** 状态变更回调（写入 Zustand 连接状态 store）。 */
  onStatusChange?: (status: ConnectionStatus) => void
  /** WebSocket 构造工厂；缺省用全局 WebSocket。 */
  factory?: WebSocketFactory
  /** 退避策略；缺省 1s→30s、±20% 抖动。 */
  policy?: ReconnectPolicy
  /** 心跳超时毫秒数；缺省 45s（§7.3）。 */
  heartbeatTimeoutMs?: number
  /** 随机源（测试注入固定值）。 */
  random?: () => number
}

/** 把 REST 同源地址映射为 WS 地址：http(s):// → ws(s)://。 */
export function wsUrl(
  path: string,
  origin: string = window.location.origin,
): string {
  return origin.replace(/^http/, 'ws') + path
}

export class WsConnection {
  readonly #url: string
  readonly #onMessage: (raw: unknown) => void
  readonly #onStatusChange?: (status: ConnectionStatus) => void
  readonly #factory: WebSocketFactory
  readonly #policy: ReconnectPolicy
  readonly #heartbeatTimeoutMs: number
  readonly #random: () => number

  #ws: WebSocketLike | null = null
  #status: ConnectionStatus = 'closed'
  #attempt = 0
  #stopped = true
  #reconnectTimer: ReturnType<typeof setTimeout> | null = null
  #heartbeatTimer: ReturnType<typeof setTimeout> | null = null

  constructor(options: WsConnectionOptions) {
    this.#url = options.url
    this.#onMessage = options.onMessage
    this.#onStatusChange = options.onStatusChange
    this.#factory =
      options.factory ?? ((url) => new WebSocket(url) as WebSocketLike)
    this.#policy = options.policy ?? DEFAULT_RECONNECT_POLICY
    this.#heartbeatTimeoutMs =
      options.heartbeatTimeoutMs ?? HEARTBEAT_TIMEOUT_MS
    this.#random = options.random ?? Math.random
  }

  get status(): ConnectionStatus {
    return this.#status
  }

  /** 建立连接；重复调用幂等。 */
  start(): void {
    if (!this.#stopped) return
    this.#stopped = false
    this.#attempt = 0
    this.#setStatus('connecting')
    this.#connect()
  }

  /** 关闭连接并停止一切重连/心跳；重复调用幂等。 */
  stop(): void {
    if (this.#stopped && this.#status === 'closed') return
    this.#stopped = true
    this.#clearTimers()
    const ws = this.#ws
    this.#ws = null
    if (ws) {
      this.#detach(ws)
      ws.close()
    }
    this.#setStatus('closed')
  }

  #setStatus(status: ConnectionStatus): void {
    if (this.#status === status) return
    this.#status = status
    this.#onStatusChange?.(status)
  }

  #clearTimers(): void {
    if (this.#reconnectTimer !== null) {
      clearTimeout(this.#reconnectTimer)
      this.#reconnectTimer = null
    }
    this.#clearHeartbeat()
  }

  #clearHeartbeat(): void {
    if (this.#heartbeatTimer !== null) {
      clearTimeout(this.#heartbeatTimer)
      this.#heartbeatTimer = null
    }
  }

  /** 收到任何消息都重置心跳；超时则主动断开走重连路径。 */
  #resetHeartbeat(): void {
    this.#clearHeartbeat()
    this.#heartbeatTimer = setTimeout(() => {
      this.#ws?.close()
    }, this.#heartbeatTimeoutMs)
  }

  #detach(ws: WebSocketLike): void {
    ws.onopen = null
    ws.onmessage = null
    ws.onclose = null
    ws.onerror = null
  }

  #connect(): void {
    const ws = this.#factory(this.#url)
    this.#ws = ws

    ws.onopen = () => {
      if (this.#ws !== ws) return
      this.#attempt = 0
      this.#setStatus('open')
      this.#resetHeartbeat()
    }

    ws.onmessage = (event) => {
      if (this.#ws !== ws) return
      // 任何帧都证明链路存活（含 ping/无法解析的帧）
      this.#resetHeartbeat()
      if (typeof event.data !== 'string') return
      let parsed: unknown
      try {
        parsed = JSON.parse(event.data)
      } catch {
        return // 非 JSON 帧静默丢弃
      }
      this.#onMessage(parsed)
    }

    ws.onclose = () => {
      if (this.#ws !== ws) return
      this.#ws = null
      this.#clearHeartbeat()
      if (this.#stopped) return
      this.#scheduleReconnect()
    }

    // error 后浏览器必随 close，统一在 close 中处理，避免双重重连。
    ws.onerror = () => undefined
  }

  #scheduleReconnect(): void {
    this.#setStatus('reconnecting')
    const delay = backoffDelay(this.#attempt, this.#policy, this.#random)
    this.#attempt += 1
    this.#reconnectTimer = setTimeout(() => {
      this.#reconnectTimer = null
      if (this.#stopped) return
      this.#connect()
    }, delay)
  }
}
