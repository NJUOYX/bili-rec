/**
 * 连接状态 store 测试（§6.2/§14.4）：通道状态写入与指示灯三态聚合。
 */
import {
  selectIndicator,
  toIndicator,
  useConnectionStore,
} from '../../../src/stores/connection'

beforeEach(() => {
  useConnectionStore.setState({ events: 'closed', exceptions: 'closed' })
})

describe('useConnectionStore', () => {
  it('初始两条通道均为 closed', () => {
    const { events, exceptions } = useConnectionStore.getState()
    expect(events).toBe('closed')
    expect(exceptions).toBe('closed')
  })

  it('setStatus 独立更新单条通道', () => {
    useConnectionStore.getState().setStatus('events', 'open')
    expect(useConnectionStore.getState().events).toBe('open')
    expect(useConnectionStore.getState().exceptions).toBe('closed')
    useConnectionStore.getState().setStatus('exceptions', 'reconnecting')
    expect(useConnectionStore.getState().exceptions).toBe('reconnecting')
  })
})

describe('toIndicator 三态聚合（绿/黄/红）', () => {
  it('两条通道均 open → connected（绿）', () => {
    expect(toIndicator('open', 'open')).toBe('connected')
  })

  it.each([
    ['connecting', 'open'],
    ['open', 'connecting'],
    ['reconnecting', 'open'],
    ['reconnecting', 'closed'],
    ['connecting', 'connecting'],
  ] as const)('存在连接中/重连中（%s,%s）→ reconnecting（黄）', (a, b) => {
    expect(toIndicator(a, b)).toBe('reconnecting')
  })

  it.each([
    ['closed', 'closed'],
    ['open', 'closed'],
    ['closed', 'open'],
  ] as const)('存在 closed 且无重连中（%s,%s）→ disconnected（红）', (a, b) => {
    expect(toIndicator(a, b)).toBe('disconnected')
  })

  it('selectIndicator 从 store 状态聚合', () => {
    useConnectionStore.getState().setStatus('events', 'open')
    useConnectionStore.getState().setStatus('exceptions', 'open')
    expect(selectIndicator(useConnectionStore.getState())).toBe('connected')
  })
})
