/**
 * 指数退避重连策略测试（frontend-design.md §7.3）。
 *
 * 覆盖：指数序列、上限封顶、抖动边界、确定性（注入 random）。
 */
import {
  backoffDelay,
  DEFAULT_RECONNECT_POLICY,
  HEARTBEAT_TIMEOUT_MS,
  SERVER_PING_INTERVAL_MS,
} from '../../../src/ws/reconnect'

describe('backoffDelay', () => {
  it('无抖动时按 1s→2s→4s→8s 指数增长', () => {
    const policy = { ...DEFAULT_RECONNECT_POLICY, jitterRatio: 0 }
    expect(backoffDelay(0, policy)).toBe(1_000)
    expect(backoffDelay(1, policy)).toBe(2_000)
    expect(backoffDelay(2, policy)).toBe(4_000)
    expect(backoffDelay(3, policy)).toBe(8_000)
  })

  it('封顶于 maxDelayMs=30s（§7.3 上限 30s）', () => {
    const policy = { ...DEFAULT_RECONNECT_POLICY, jitterRatio: 0 }
    expect(backoffDelay(5, policy)).toBe(30_000)
    expect(backoffDelay(20, policy)).toBe(30_000)
    // 极大 attempt 不溢出
    expect(backoffDelay(1000, policy)).toBe(30_000)
  })

  it('抖动落在 [base*(1-ratio), base*(1+ratio)] 区间内', () => {
    // random() = 0 → 下界；random() = 1 → 上界（不含），取近似断言
    const low = backoffDelay(2, DEFAULT_RECONNECT_POLICY, () => 0)
    const high = backoffDelay(2, DEFAULT_RECONNECT_POLICY, () => 0.999999)
    const ratio = DEFAULT_RECONNECT_POLICY.jitterRatio
    expect(low).toBe(4_000 * (1 - ratio))
    expect(high).toBeGreaterThan(4_000)
    expect(high).toBeLessThanOrEqual(4_000 * (1 + ratio))
  })

  it('注入固定 random 时结果确定', () => {
    const rand = () => 0.5
    expect(backoffDelay(1, DEFAULT_RECONNECT_POLICY, rand)).toBe(
      backoffDelay(1, DEFAULT_RECONNECT_POLICY, rand),
    )
  })

  it('结果永不为负', () => {
    expect(backoffDelay(0, DEFAULT_RECONNECT_POLICY, () => 0)).toBeGreaterThan(
      0,
    )
  })
})

describe('心跳常量（§7.1/§7.3）', () => {
  it('服务端 ping 间隔 30s，心跳超时 45s（> ping 间隔）', () => {
    expect(SERVER_PING_INTERVAL_MS).toBe(30_000)
    expect(HEARTBEAT_TIMEOUT_MS).toBe(45_000)
    expect(HEARTBEAT_TIMEOUT_MS).toBeGreaterThan(SERVER_PING_INTERVAL_MS)
  })
})
