/**
 * 指数退避重连与心跳策略（frontend-design.md §7.3）。
 *
 * - 退避序列：1s → 2s → 4s → …，封顶 30s，带 ±jitterRatio 抖动
 *   （避免多标签页/多连接同时重连造成后端瞬时压力）。
 * - 心跳：后端空闲 30s 发送 `{type:"ping"}`（§7.1）；前端若超过 45s
 *   未收到任何消息，判定连接假死，主动断开触发重连。
 *
 * 纯函数 + 常量，便于确定性单测（注入 random）。
 */

/** 后端空闲 ping 间隔（web/routers/websocket.py，30s）。 */
export const SERVER_PING_INTERVAL_MS = 30_000

/** 心跳超时：>45s（> ping 间隔）未收到任何消息则断开重连（§7.3）。 */
export const HEARTBEAT_TIMEOUT_MS = 45_000

/** 退避策略参数。 */
export interface ReconnectPolicy {
  /** 首次重连延迟（毫秒）。 */
  baseDelayMs: number
  /** 延迟上限（毫秒）。 */
  maxDelayMs: number
  /** 抖动比例：结果落在 [delay*(1-r), delay*(1+r))。 */
  jitterRatio: number
}

/** 默认策略：1s 起步、30s 封顶、±20% 抖动。 */
export const DEFAULT_RECONNECT_POLICY: ReconnectPolicy = {
  baseDelayMs: 1_000,
  maxDelayMs: 30_000,
  jitterRatio: 0.2,
}

/**
 * 计算第 `attempt` 次（从 0 计）重连的延迟毫秒数。
 * 指数部分用 `min(2^attempt, max/base)` 防止大指数溢出。
 */
export function backoffDelay(
  attempt: number,
  policy: ReconnectPolicy = DEFAULT_RECONNECT_POLICY,
  random: () => number = Math.random,
): number {
  const cappedExponent = Math.min(attempt, 31)
  const raw = Math.min(
    policy.baseDelayMs * 2 ** cappedExponent,
    policy.maxDelayMs,
  )
  // 抖动映射：random() ∈ [0,1) → 系数 ∈ [1-r, 1+r)
  const factor = 1 + policy.jitterRatio * (random() * 2 - 1)
  return raw * factor
}
