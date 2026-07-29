/**
 * M30 DT：ConnectionIndicator / ThemeToggle / EventLogPanel
 * （frontend-design.md §14.3/§14.4/§10.1）。
 */
import { act, fireEvent, render, screen } from '@testing-library/react'

import { ConnectionIndicator } from '../../../src/components/ConnectionIndicator'
import {
  describeEvent,
  EVENT_TYPE_LABELS,
  EventLogPanel,
} from '../../../src/components/EventLogPanel'
import { nextThemeMode, ThemeToggle } from '../../../src/components/ThemeToggle'
import { useConnectionStore } from '../../../src/stores/connection'
import { useEventLogStore } from '../../../src/stores/eventLog'
import { THEME_STORAGE_KEY, useThemeStore } from '../../../src/stores/theme'
import type { AppEvent, ErrorEvent, FileEvent } from '../../../src/ws/events'

function makeFileEvent(overrides: Partial<FileEvent> = {}): FileEvent {
  return {
    type: 'VideoFileCreatedEvent',
    id: 'evt-1',
    date: '2026-07-29T10:00:00+08:00',
    data: { room_id: 23058, path: '/rec/a.flv' },
    ...overrides,
  }
}

beforeEach(() => {
  act(() => {
    useConnectionStore.setState({ events: 'closed', exceptions: 'closed' })
    useEventLogStore.getState().clear()
  })
})

describe('ConnectionIndicator', () => {
  it.each([
    ['open', 'open', 'connected', '已连接'],
    ['reconnecting', 'open', 'reconnecting', '重连中'],
    ['closed', 'open', 'disconnected', '已断开'],
  ] as const)(
    'events=%s exceptions=%s → %s',
    (events, exceptions, state, text) => {
      act(() => {
        useConnectionStore.setState({ events, exceptions })
      })
      render(<ConnectionIndicator />)
      const el = screen.getByTestId('connection-indicator')
      expect(el.dataset.state).toBe(state)
      expect(el.textContent).toContain(text)
    },
  )
})

describe('ThemeToggle', () => {
  afterEach(() => {
    act(() => useThemeStore.getState().setMode('system'))
    window.localStorage.removeItem(THEME_STORAGE_KEY)
  })

  it('nextThemeMode 三态循环', () => {
    expect(nextThemeMode('system')).toBe('light')
    expect(nextThemeMode('light')).toBe('dark')
    expect(nextThemeMode('dark')).toBe('system')
  })

  it('点击按序切换并持久化', () => {
    render(<ThemeToggle />)
    const button = screen.getByTestId('theme-toggle')
    fireEvent.click(button)
    expect(useThemeStore.getState().mode).toBe('light')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    fireEvent.click(button)
    expect(useThemeStore.getState().mode).toBe('dark')
    fireEvent.click(button)
    expect(useThemeStore.getState().mode).toBe('system')
  })
})

describe('EventLogPanel', () => {
  it('空状态渲染 Empty', () => {
    render(<EventLogPanel />)
    expect(screen.getByTestId('event-log-empty')).toBeTruthy()
  })

  it('渲染事件列表（类型标签+描述）', () => {
    act(() => {
      useEventLogStore.getState().pushEvent(makeFileEvent())
    })
    render(<EventLogPanel />)
    expect(screen.getByText('视频文件创建')).toBeTruthy()
    expect(screen.getAllByText(/23058/).length).toBeGreaterThan(0)
  })

  it('limit 截断（紧凑态）', () => {
    act(() => {
      for (let i = 0; i < 5; i += 1) {
        useEventLogStore.getState().pushEvent(makeFileEvent({ id: `evt-${i}` }))
      }
    })
    render(<EventLogPanel limit={2} />)
    expect(screen.getAllByText('视频文件创建')).toHaveLength(2)
  })

  it('describeEvent 各分支', () => {
    expect(describeEvent(makeFileEvent())).toBe('房间 23058 · /rec/a.flv')
    const err: ErrorEvent = {
      type: 'Error',
      id: 'e',
      date: '2026-07-29T10:00:00+08:00',
      data: { name: 'OSError', detail: 'disk full' },
    }
    expect(describeEvent(err)).toBe('OSError: disk full')
    const done: AppEvent = {
      type: 'PostprocessingCompletedEvent',
      id: 'p',
      date: '2026-07-29T10:00:00+08:00',
      data: { room_id: 1, files: ['a.mp4', 'b.xml'] },
    }
    expect(describeEvent(done)).toBe('房间 1 · 2 个产物')
  })

  it('标签映射覆盖全部事件类型', () => {
    expect(Object.keys(EVENT_TYPE_LABELS)).toHaveLength(10)
  })
})
