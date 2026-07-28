/**
 * Mock WebSocket 测试辅助：无真实网络，手动驱动 open/message/close/error。
 * 配合 vi.useFakeTimers 实现连接管理器的确定性测试。
 */

type Handler<E> = ((event: E) => void) | null

export class MockWebSocket {
  static instances: MockWebSocket[] = []

  static reset(): void {
    MockWebSocket.instances = []
  }

  /** 最近创建的实例（当前活跃连接）。 */
  static latest(): MockWebSocket {
    const last = MockWebSocket.instances.at(-1)
    if (!last) throw new Error('No MockWebSocket instance created')
    return last
  }

  readonly url: string
  /** 0=CONNECTING 1=OPEN 3=CLOSED（与真实 WebSocket 对齐）。 */
  readyState = 0
  closeCalls = 0

  onopen: Handler<unknown> = null
  onmessage: Handler<{ data: unknown }> = null
  onclose: Handler<unknown> = null
  onerror: Handler<unknown> = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  /** 客户端主动 close：同步触发 close 事件（真实实现为异步，语义一致）。 */
  close(): void {
    this.closeCalls += 1
    if (this.readyState === 3) return
    this.readyState = 3
    this.onclose?.({})
  }

  simulateOpen(): void {
    this.readyState = 1
    this.onopen?.({})
  }

  /** 模拟收到服务端 JSON 消息。 */
  simulateMessage(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) })
  }

  /** 模拟收到无法解析/非字符串的帧。 */
  simulateRawMessage(data: unknown): void {
    this.onmessage?.({ data })
  }

  /** 模拟服务端断开/网络中断。 */
  simulateClose(): void {
    this.readyState = 3
    this.onclose?.({})
  }

  simulateError(): void {
    this.onerror?.({})
  }
}
