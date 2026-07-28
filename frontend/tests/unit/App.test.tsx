import { render, screen } from '@testing-library/react'
import App from '../../src/App'
import { useRealtime } from '../../src/ws/useRealtime'

// 隔离 WS 副作用：App 装配测试只验证「渲染外壳 + 接线 useRealtime」，
// 实时层行为由 tests/unit/ws/ 各测试专门覆盖。
vi.mock('../../src/ws/useRealtime', () => ({ useRealtime: vi.fn() }))

describe('App', () => {
  it('渲染应用标题', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { level: 1, name: 'bili-rec' }),
    ).toBeTruthy()
  })

  it('挂载即接线实时推送（useRealtime，§7.3）', () => {
    render(<App />)
    expect(vi.mocked(useRealtime)).toHaveBeenCalled()
  })
})
