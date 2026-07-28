/**
 * 事件/异常日志 store 测试（§7.4/§9）：入栈顺序、有界缓冲、清空。
 */
import { MAX_LOG_ENTRIES, useEventLogStore } from '../../../src/stores/eventLog'
import type { AppEvent } from '../../../src/ws/events'

function makeErrorEvent(detail: string): AppEvent {
  return {
    type: 'Error',
    id: `id-${detail}`,
    date: '2026-07-28T12:00:00+08:00',
    data: { name: 'RuntimeError', detail },
  }
}

beforeEach(() => {
  useEventLogStore.getState().clear()
})

describe('useEventLogStore', () => {
  it('pushEvent 最新在前', () => {
    const { pushEvent } = useEventLogStore.getState()
    pushEvent(makeErrorEvent('first'))
    pushEvent(makeErrorEvent('second'))
    const events = useEventLogStore.getState().events
    expect(events).toHaveLength(2)
    expect(events[0].data).toMatchObject({ detail: 'second' })
    expect(events[1].data).toMatchObject({ detail: 'first' })
  })

  it('事件缓冲有界：超出上限丢弃最旧条目', () => {
    const { pushEvent } = useEventLogStore.getState()
    for (let i = 0; i < MAX_LOG_ENTRIES + 5; i += 1) {
      pushEvent(makeErrorEvent(`e${i}`))
    }
    const events = useEventLogStore.getState().events
    expect(events).toHaveLength(MAX_LOG_ENTRIES)
    expect(events[0].data).toMatchObject({ detail: `e${MAX_LOG_ENTRIES + 4}` })
  })

  it('pushException 记录消息与接收时间', () => {
    useEventLogStore
      .getState()
      .pushException(
        { type: 'RuntimeError', message: 'boom', traceback: 'tb' },
        '2026-07-28T12:34:56Z',
      )
    const entries = useEventLogStore.getState().exceptions
    expect(entries).toHaveLength(1)
    expect(entries[0].message.message).toBe('boom')
    expect(entries[0].receivedAt).toBe('2026-07-28T12:34:56Z')
  })

  it('pushException 缺省接收时间取当前时刻（ISO 格式）', () => {
    useEventLogStore
      .getState()
      .pushException({ type: 'E', message: 'm', traceback: 't' })
    const entry = useEventLogStore.getState().exceptions[0]
    expect(() => new Date(entry.receivedAt)).not.toThrow()
    expect(Number.isNaN(Date.parse(entry.receivedAt))).toBe(false)
  })

  it('异常缓冲有界', () => {
    const { pushException } = useEventLogStore.getState()
    for (let i = 0; i < MAX_LOG_ENTRIES + 3; i += 1) {
      pushException({ type: 'E', message: `m${i}`, traceback: 't' })
    }
    expect(useEventLogStore.getState().exceptions).toHaveLength(MAX_LOG_ENTRIES)
  })

  it('clear 清空两类日志', () => {
    const state = useEventLogStore.getState()
    state.pushEvent(makeErrorEvent('x'))
    state.pushException({ type: 'E', message: 'm', traceback: 't' })
    useEventLogStore.getState().clear()
    expect(useEventLogStore.getState().events).toEqual([])
    expect(useEventLogStore.getState().exceptions).toEqual([])
  })
})
