/**
 * useEventStream hook 测试（§7.1-§7.4）：
 * 连接建立/默认地址、状态写入 store、事件入日志 + 缓存失效、
 * ping/畸形载荷过滤、卸载关闭连接。
 */
import { QueryClient } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'

import { queryKeys } from '../../../src/api/queryKeys'
import { useConnectionStore } from '../../../src/stores/connection'
import { useEventLogStore } from '../../../src/stores/eventLog'
import { useEventStream } from '../../../src/ws/useEventStream'
import { MockWebSocket } from '../helpers/ws'
import { createQueryWrapper, createTestQueryClient } from '../helpers/query'

const factory = (url: string) => new MockWebSocket(url)

function renderStream(client: QueryClient = createTestQueryClient()) {
  const view = renderHook(() => useEventStream({ factory }), {
    wrapper: createQueryWrapper(client),
  })
  return { client, ...view }
}

beforeEach(() => {
  MockWebSocket.reset()
  useConnectionStore.setState({ events: 'closed', exceptions: 'closed' })
  useEventLogStore.getState().clear()
})

describe('useEventStream', () => {
  it('挂载即连接默认地址 /ws/v1/events，状态写入 events 通道', () => {
    renderStream()
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1)
    expect(MockWebSocket.latest().url).toMatch(/^ws:.*\/ws\/v1\/events$/)
    expect(useConnectionStore.getState().events).toBe('connecting')
    MockWebSocket.latest().simulateOpen()
    expect(useConnectionStore.getState().events).toBe('open')
    // exceptions 通道不受影响
    expect(useConnectionStore.getState().exceptions).toBe('closed')
  })

  it('业务事件 → 入事件日志并按 §7.4 失效缓存', () => {
    const client = createTestQueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    renderStream(client)
    MockWebSocket.latest().simulateOpen()
    MockWebSocket.latest().simulateMessage({
      type: 'VideoFileCompletedEvent',
      id: 'id-1',
      date: '2026-07-28T12:00:00+08:00',
      data: { room_id: 123, path: '/rec/a.flv' },
    })
    expect(useEventLogStore.getState().events).toHaveLength(1)
    expect(spy.mock.calls.map(([f]) => f?.queryKey)).toEqual([
      queryKeys.task(123, 'videos'),
      queryKeys.task(123, 'data'),
    ])
  })

  it('ping 仅判活：不入日志、不失效缓存', () => {
    const client = createTestQueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    renderStream(client)
    MockWebSocket.latest().simulateOpen()
    MockWebSocket.latest().simulateMessage({ type: 'ping' })
    expect(useEventLogStore.getState().events).toEqual([])
    expect(spy).not.toHaveBeenCalled()
  })

  it('畸形载荷静默丢弃', () => {
    renderStream()
    MockWebSocket.latest().simulateOpen()
    MockWebSocket.latest().simulateMessage({ type: 'NotARealEvent', x: 1 })
    MockWebSocket.latest().simulateRawMessage('{bad json')
    expect(useEventLogStore.getState().events).toEqual([])
  })

  it('卸载后关闭连接，状态回到 closed', () => {
    const { unmount } = renderStream()
    MockWebSocket.latest().simulateOpen()
    unmount()
    expect(useConnectionStore.getState().events).toBe('closed')
    expect(MockWebSocket.latest().readyState).toBe(3)
  })
})
