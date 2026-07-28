/**
 * useRealtime 总线 hook 测试（§7.3：页面加载即建立两条连接）。
 */
import { renderHook } from '@testing-library/react'

import { useConnectionStore } from '../../../src/stores/connection'
import { useRealtime } from '../../../src/ws/useRealtime'
import { MockWebSocket } from '../helpers/ws'
import { createQueryWrapper } from '../helpers/query'

beforeEach(() => {
  MockWebSocket.reset()
  useConnectionStore.setState({ events: 'closed', exceptions: 'closed' })
  // 缺省工厂走全局 WebSocket：stub 为 Mock，避免 jsdom 发起真实连接
  vi.stubGlobal('WebSocket', MockWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useRealtime', () => {
  it('同时建立 events 与 exceptions 两条连接并写入各自通道状态', () => {
    const { unmount } = renderHook(() => useRealtime(), {
      wrapper: createQueryWrapper(),
    })
    const urls = MockWebSocket.instances.map((ws) => ws.url)
    expect(urls.some((u) => u.endsWith('/ws/v1/events'))).toBe(true)
    expect(urls.some((u) => u.endsWith('/ws/v1/exceptions'))).toBe(true)
    expect(useConnectionStore.getState().events).toBe('connecting')
    expect(useConnectionStore.getState().exceptions).toBe('connecting')
    unmount()
    expect(useConnectionStore.getState().events).toBe('closed')
    expect(useConnectionStore.getState().exceptions).toBe('closed')
  })
})
