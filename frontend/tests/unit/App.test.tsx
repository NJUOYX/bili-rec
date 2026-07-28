import { render, screen } from '@testing-library/react'
import App from '../../src/App'

// M27 冒烟测试：验证测试栈（Vitest + jsdom + RTL）可用，
// 应用外壳能渲染出标题。功能测试随后续里程碑补充。
describe('App', () => {
  it('渲染应用标题', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { level: 1, name: 'bili-rec' }),
    ).toBeTruthy()
  })
})
