/**
 * useExceptionStream hook 测试（§7.1/§9）：
 * 连接建立/默认地址、状态写入 exceptions 通道、异常入日志、
 * ping/畸形载荷过滤、卸载关闭连接。
 */
import { renderHook } from '@testing-library/react'

import { useConnectionStore } from '../../../src/stores/connection'
import { useEventLogStore } from '../../../src/stores/eventLog'
import { useExceptionStream } from '../../../src/ws/useExceptionStream'
import { MockWebSocket } from '../helpers/ws'

const factory = (url: string) => new MockWebSocket(url)

beforeEach(() => {
  MockWebSocket.reset()
  useConnectionStore.setState({ events: 'closed', exceptions: 'closed' })
  useEventLogStore.getState().clear()
})

describe('useExceptionStream', () => {
  it('挂载即连接默认地址 /ws/v1/exceptions，状态写入 exceptions 通道', () => {
    renderHook(() => useExceptionStream({ factory }))
    expect(MockWebSocket.latest().url).toMatch(/^ws:.*\/ws\/v1\/exceptions$/)
    expect(useConnectionStore.getState().exceptions).toBe('connecting')
    MockWebSocket.latest().simulateOpen()
    expect(useConnectionStore.getState().exceptions).toBe('open')
    expect(useConnectionStore.getState().events).toBe('closed')
  })

  it('异常消息 {type,message,traceback} 入异常日志', () => {
    renderHook(() => useExceptionStream({ factory }))
    MockWebSocket.latest().simulateOpen()
    MockWebSocket.latest().simulateMessage({
      type: 'RuntimeError',
      message: 'boom',
      traceback: 'Traceback ...',
    })
    const entries = useEventLogStore.getState().exceptions
    expect(entries).toHaveLength(1)
    expect(entries[0].message).toEqual({
      type: 'RuntimeError',
      message: 'boom',
      traceback: 'Traceback ...',
    })
  })

  it('ping 与畸形载荷均不入日志', () => {
    renderHook(() => useExceptionStream({ factory }))
    MockWebSocket.latest().simulateOpen()
    MockWebSocket.latest().simulateMessage({ type: 'ping' })
    MockWebSocket.latest().simulateMessage({ type: 'E', message: 'no tb' })
    MockWebSocket.latest().simulateRawMessage('{bad')
    expect(useEventLogStore.getState().exceptions).toEqual([])
  })

  it('卸载后关闭连接，状态回到 closed', () => {
    const { unmount } = renderHook(() => useExceptionStream({ factory }))
    MockWebSocket.latest().simulateOpen()
    unmount()
    expect(useConnectionStore.getState().exceptions).toBe('closed')
    expect(MockWebSocket.latest().readyState).toBe(3)
  })
})
