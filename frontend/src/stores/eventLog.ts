/**
 * 事件/异常日志 store（Zustand，frontend-design.md §7.4/§9/§14.5）。
 *
 * `/ws/v1/events` 的业务事件与 `/ws/v1/exceptions` 的异常消息汇入此处，
 * 供 Dashboard「最近事件时间线」与「事件/异常」面板（EventLogPanel，M30+）
 * 消费。有界缓冲（最新在前），防止长时间运行内存膨胀。
 */
import { create } from 'zustand'

import type { AppEvent, ExceptionMessage } from '../ws/events'

/** 缓冲上限：超过后丢弃最旧条目。 */
export const MAX_LOG_ENTRIES = 100

/** 异常条目附加接收时间（异常消息本身无时间戳）。 */
export interface ExceptionEntry {
  message: ExceptionMessage
  receivedAt: string
}

export interface EventLogState {
  events: AppEvent[]
  exceptions: ExceptionEntry[]
  pushEvent: (event: AppEvent) => void
  pushException: (message: ExceptionMessage, receivedAt?: string) => void
  clear: () => void
}

export const useEventLogStore = create<EventLogState>()((set) => ({
  events: [],
  exceptions: [],
  pushEvent: (event) =>
    set((state) => ({
      events: [event, ...state.events].slice(0, MAX_LOG_ENTRIES),
    })),
  pushException: (message, receivedAt = new Date().toISOString()) =>
    set((state) => ({
      exceptions: [{ message, receivedAt }, ...state.exceptions].slice(
        0,
        MAX_LOG_ENTRIES,
      ),
    })),
  clear: () => set({ events: [], exceptions: [] }),
}))
