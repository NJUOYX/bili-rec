/**
 * M30 DT：TaskCard 交互（启停/录制器开关，§14.6）。
 * 注：AntD 会在两个中文字符间插入空格、图标 aria-label 会并入按钮可及名，
 * 故按钮以宽松正则匹配。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { AppProviders } from '../../../src/app/providers'
import {
  TaskCard,
  type TaskCardActions,
} from '../../../src/components/TaskCard'
import { parseTaskData, type TaskDataView } from '../../../src/lib/task'
import { makeTaskDataRaw } from '../helpers/fixtures'
import { createPageQueryClient } from '../helpers/render'

function view(
  overrides: Record<string, unknown> = {},
  statusOverrides: Record<string, unknown> = {},
): TaskDataView {
  const parsed = parseTaskData(makeTaskDataRaw(overrides, statusOverrides))
  if (!parsed) throw new Error('fixture parse failed')
  return parsed
}

function renderCard(
  task: TaskDataView,
  actions: Partial<TaskCardActions> = {},
  busy = false,
) {
  const handlers: TaskCardActions = {
    onStart: vi.fn(),
    onStop: vi.fn(),
    onToggleRecorder: vi.fn(),
    onRefresh: vi.fn(),
    onDelete: vi.fn(),
    ...actions,
  }
  const result = render(
    <AppProviders queryClient={createPageQueryClient()}>
      <MemoryRouter>
        <TaskCard task={task} busy={busy} {...handlers} />
      </MemoryRouter>
    </AppProviders>,
  )
  return { ...handlers, container: result.container }
}

describe('TaskCard', () => {
  it('监控开启时展示停止按钮并回调 onStop', () => {
    const h = renderCard(view({}, { monitor_enabled: true }))
    fireEvent.click(screen.getByRole('button', { name: /停\s*止/ }))
    expect(h.onStop).toHaveBeenCalledWith(23058)
  })

  it('监控关闭时展示启动按钮并回调 onStart', () => {
    const h = renderCard(
      view({}, { monitor_enabled: false, running_status: 'stopped' }),
    )
    fireEvent.click(screen.getByRole('button', { name: /启\s*动/ }))
    expect(h.onStart).toHaveBeenCalledWith(23058)
  })

  it('录制器开关回调 onToggleRecorder', () => {
    const h = renderCard(view({}, { recorder_enabled: false }))
    fireEvent.click(screen.getByRole('switch', { name: '录制器开关' }))
    expect(h.onToggleRecorder).toHaveBeenCalledWith(23058, true)
  })

  it('busy 时禁用停止按钮', () => {
    renderCard(view({}, { monitor_enabled: true }), {}, true)
    const stop = screen.getByRole('button', {
      name: /停\s*止/,
    }) as HTMLButtonElement
    expect(stop.disabled).toBe(true)
  })

  it('非录制态不渲染速率仪表', () => {
    renderCard(view({}, { running_status: 'waiting' }))
    expect(screen.queryByTestId('rate-gauge')).toBeNull()
  })

  it('录制态渲染速率仪表', () => {
    renderCard(view({}, { running_status: 'recording' }))
    expect(screen.getByTestId('rate-gauge')).toBeTruthy()
  })

  it('有 cover_url 时渲染封面图片', () => {
    const { container } = renderCard(
      view({ cover_url: 'https://cdn.example.com/cover.jpg' }),
    )
    const img = container.querySelector('img')
    expect(img).toBeTruthy()
    expect(img!.getAttribute('src')).toBe('https://cdn.example.com/cover.jpg')
  })

  it('无 cover_url 时降级为分区名占位', () => {
    const { container } = renderCard(view({ cover_url: '' }))
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('娱乐')).toBeTruthy()
  })

  it('封面图片加载失败时降级为分区名占位', () => {
    const { container } = renderCard(
      view({ cover_url: 'https://cdn.example.com/broken.jpg' }),
    )
    const img = container.querySelector('img')
    expect(img).toBeTruthy()
    fireEvent.error(img!)
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('娱乐')).toBeTruthy()
  })
})
