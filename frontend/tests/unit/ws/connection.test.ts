/**
 * WsConnection 连接管理器测试（frontend-design.md §7.3）。
 *
 * 用 MockWebSocket + fake timers 覆盖：连接/状态回调、消息分发、
 * 心跳超时断开重连、指数退避序列、成功后计数重置、stop 幂等。
 */
import { WsConnection, wsUrl } from '../../../src/ws/connection'
import type { ConnectionStatus } from '../../../src/ws/connection'
import { MockWebSocket } from '../helpers/ws'

/** 零抖动策略：延迟确定为 1s→2s→4s→…→30s。 */
const NO_JITTER = { baseDelayMs: 1_000, maxDelayMs: 30_000, jitterRatio: 0 }

function makeConnection(overrides?: {
  onMessage?: (raw: unknown) => void
  onStatusChange?: (status: ConnectionStatus) => void
  heartbeatTimeoutMs?: number
}) {
  const messages: unknown[] = []
  const statuses: ConnectionStatus[] = []
  const conn = new WsConnection({
    url: 'ws://test/ws/v1/events',
    onMessage: overrides?.onMessage ?? ((raw) => messages.push(raw)),
    onStatusChange:
      overrides?.onStatusChange ?? ((status) => statuses.push(status)),
    factory: (url) => new MockWebSocket(url),
    policy: NO_JITTER,
    heartbeatTimeoutMs: overrides?.heartbeatTimeoutMs,
  })
  return { conn, messages, statuses }
}

beforeEach(() => {
  vi.useFakeTimers()
  MockWebSocket.reset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('WsConnection 基本生命周期', () => {
  it('start 后进入 connecting，open 后进入 open', () => {
    const { conn, statuses } = makeConnection()
    expect(conn.status).toBe('closed')
    conn.start()
    expect(conn.status).toBe('connecting')
    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.latest().url).toBe('ws://test/ws/v1/events')
    MockWebSocket.latest().simulateOpen()
    expect(conn.status).toBe('open')
    expect(statuses).toEqual(['connecting', 'open'])
  })

  it('start 幂等：重复调用不会创建第二条连接', () => {
    const { conn } = makeConnection()
    conn.start()
    conn.start()
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('stop 后进入 closed、关闭底层连接且不再重连', () => {
    const { conn } = makeConnection()
    conn.start()
    const ws = MockWebSocket.latest()
    ws.simulateOpen()
    conn.stop()
    expect(conn.status).toBe('closed')
    expect(ws.closeCalls).toBe(1)
    vi.advanceTimersByTime(120_000)
    expect(MockWebSocket.instances).toHaveLength(1)
    // stop 幂等
    conn.stop()
    expect(conn.status).toBe('closed')
  })
})

describe('WsConnection 消息分发', () => {
  it('JSON 消息解析后分发给 onMessage（含 ping，过滤交由上层）', () => {
    const { conn, messages } = makeConnection()
    conn.start()
    const ws = MockWebSocket.latest()
    ws.simulateOpen()
    ws.simulateMessage({ type: 'ping' })
    ws.simulateMessage({ type: 'Error', data: { name: 'E', detail: 'd' } })
    expect(messages).toEqual([
      { type: 'ping' },
      { type: 'Error', data: { name: 'E', detail: 'd' } },
    ])
  })

  it('非 JSON / 非字符串帧静默忽略，不崩溃不分发', () => {
    const { conn, messages } = makeConnection()
    conn.start()
    const ws = MockWebSocket.latest()
    ws.simulateOpen()
    ws.simulateRawMessage('{not json')
    ws.simulateRawMessage(new ArrayBuffer(4))
    expect(messages).toEqual([])
    expect(conn.status).toBe('open')
  })
})

describe('WsConnection 心跳（§7.3：>45s 无消息则断开重连）', () => {
  it('超过 45s 未收到任何消息 → 主动断开并进入 reconnecting', () => {
    const { conn } = makeConnection()
    conn.start()
    const ws = MockWebSocket.latest()
    ws.simulateOpen()
    vi.advanceTimersByTime(45_000)
    expect(ws.closeCalls).toBe(1)
    expect(conn.status).toBe('reconnecting')
  })

  it('任何消息（含 ping）都重置心跳计时', () => {
    const { conn } = makeConnection()
    conn.start()
    const ws = MockWebSocket.latest()
    ws.simulateOpen()
    vi.advanceTimersByTime(40_000)
    ws.simulateMessage({ type: 'ping' }) // 判活
    vi.advanceTimersByTime(40_000) // 距上次消息仅 40s
    expect(ws.closeCalls).toBe(0)
    expect(conn.status).toBe('open')
    vi.advanceTimersByTime(5_000) // 距上次消息 45s
    expect(ws.closeCalls).toBe(1)
  })

  it('stop 后心跳计时器清理，不再触发断开', () => {
    const { conn } = makeConnection()
    conn.start()
    MockWebSocket.latest().simulateOpen()
    conn.stop()
    vi.advanceTimersByTime(60_000)
    expect(conn.status).toBe('closed')
  })
})

describe('WsConnection 指数退避重连（§7.3）', () => {
  it('意外断开 → reconnecting，按 1s→2s→4s 序列重试', () => {
    const { conn, statuses } = makeConnection()
    conn.start()
    MockWebSocket.latest().simulateClose() // 第 1 次失败
    expect(conn.status).toBe('reconnecting')
    expect(MockWebSocket.instances).toHaveLength(1)

    vi.advanceTimersByTime(999)
    expect(MockWebSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(1) // 1s 到 → 第 2 条连接
    expect(MockWebSocket.instances).toHaveLength(2)

    MockWebSocket.latest().simulateClose() // 第 2 次失败
    vi.advanceTimersByTime(2_000) // 2s → 第 3 条
    expect(MockWebSocket.instances).toHaveLength(3)

    MockWebSocket.latest().simulateClose() // 第 3 次失败
    vi.advanceTimersByTime(3_999)
    expect(MockWebSocket.instances).toHaveLength(3)
    vi.advanceTimersByTime(1) // 4s → 第 4 条
    expect(MockWebSocket.instances).toHaveLength(4)
    // 状态回调去重：连续失败期间保持 reconnecting，仅回调一次
    expect(statuses).toEqual(['connecting', 'reconnecting'])
  })

  it('重连成功后退避计数重置：再次断开从 1s 重新起步', () => {
    const { conn } = makeConnection()
    conn.start()
    MockWebSocket.latest().simulateClose()
    vi.advanceTimersByTime(1_000)
    MockWebSocket.latest().simulateClose()
    vi.advanceTimersByTime(2_000)
    MockWebSocket.latest().simulateOpen() // 成功 → 计数重置
    expect(conn.status).toBe('open')

    MockWebSocket.latest().simulateClose() // 再次断开
    vi.advanceTimersByTime(1_000) // 应回到 1s 起步
    expect(MockWebSocket.instances).toHaveLength(4)
  })

  it('心跳超时触发的断开同样走退避重连并恢复', () => {
    const { conn, messages } = makeConnection()
    conn.start()
    MockWebSocket.latest().simulateOpen()
    vi.advanceTimersByTime(45_000) // 心跳超时
    vi.advanceTimersByTime(1_000) // 退避 1s 后重建
    expect(MockWebSocket.instances).toHaveLength(2)
    MockWebSocket.latest().simulateOpen()
    expect(conn.status).toBe('open')
    MockWebSocket.latest().simulateMessage({ type: 'ping' })
    expect(messages).toEqual([{ type: 'ping' }])
  })

  it('error 事件不独立触发重连（浏览器 error 后必随 close，避免双重重连）', () => {
    const { conn } = makeConnection()
    conn.start()
    const ws = MockWebSocket.latest()
    ws.simulateOpen()
    ws.simulateError()
    expect(conn.status).toBe('open')
    ws.simulateClose()
    expect(conn.status).toBe('reconnecting')
    vi.advanceTimersByTime(1_000)
    expect(MockWebSocket.instances).toHaveLength(2)
  })
})

describe('wsUrl', () => {
  it('http 源映射为 ws', () => {
    expect(wsUrl('/ws/v1/events', 'http://127.0.0.1:2233')).toBe(
      'ws://127.0.0.1:2233/ws/v1/events',
    )
  })

  it('https 源映射为 wss', () => {
    expect(wsUrl('/ws/v1/exceptions', 'https://example.com')).toBe(
      'wss://example.com/ws/v1/exceptions',
    )
  })

  it('缺省时取当前页面源（jsdom localhost）', () => {
    expect(wsUrl('/ws/v1/events')).toBe(
      window.location.origin.replace(/^http/, 'ws') + '/ws/v1/events',
    )
  })
})
