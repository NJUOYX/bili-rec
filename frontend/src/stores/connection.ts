/**
 * WS 连接状态 store（Zustand，frontend-design.md §6.2/§7.3/§14.4）。
 *
 * 两条通道（events/exceptions）各自维护状态；顶栏 ConnectionIndicator
 * 由 toIndicator 聚合为绿（已连）/ 黄（连接中/重连中）/ 红（断开）三态。
 */
import { create } from 'zustand'

import type { ConnectionStatus } from '../ws/connection'

/** WS 通道标识。 */
export type WsChannel = 'events' | 'exceptions'

/** 顶栏指示灯三态（§14.4：绿=已连 / 黄=重连中 / 红=断开）。 */
export type ConnectionIndicator = 'connected' | 'reconnecting' | 'disconnected'

export interface ConnectionState {
  events: ConnectionStatus
  exceptions: ConnectionStatus
  setStatus: (channel: WsChannel, status: ConnectionStatus) => void
}

export const useConnectionStore = create<ConnectionState>()((set) => ({
  events: 'closed',
  exceptions: 'closed',
  setStatus: (channel, status) => set({ [channel]: status }),
}))

/**
 * 聚合两条通道为指示灯三态：
 * - 任一通道在连接/重连过程中 → 黄（reconnecting）；
 * - 两条通道均已建立 → 绿（connected）；
 * - 其余（存在 closed）→ 红（disconnected）。
 */
export function toIndicator(
  events: ConnectionStatus,
  exceptions: ConnectionStatus,
): ConnectionIndicator {
  const statuses = [events, exceptions]
  if (statuses.some((s) => s === 'connecting' || s === 'reconnecting')) {
    return 'reconnecting'
  }
  if (statuses.every((s) => s === 'open')) {
    return 'connected'
  }
  return 'disconnected'
}

/** 便捷选择器：直接订阅聚合后的指示灯状态。 */
export function selectIndicator(state: ConnectionState): ConnectionIndicator {
  return toIndicator(state.events, state.exceptions)
}
