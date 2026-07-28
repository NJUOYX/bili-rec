/**
 * M28 DT：全局 Provider 组合（frontend-design.md §3）。
 */
import { QueryClient, useQueryClient } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'

import { AppProviders } from '../../../src/app/providers'

let seenClient: QueryClient | undefined

function Probe() {
  seenClient = useQueryClient()
  return <p>probe-ok</p>
}

describe('AppProviders', () => {
  beforeEach(() => {
    seenClient = undefined
  })

  it('渲染子节点并提供 QueryClient 上下文', () => {
    render(
      <AppProviders>
        <Probe />
      </AppProviders>,
    )
    expect(screen.getByText('probe-ok')).toBeTruthy()
    expect(seenClient).toBeInstanceOf(QueryClient)
  })

  it('优先使用注入的 QueryClient（测试隔离）', () => {
    const injected = new QueryClient()
    render(
      <AppProviders queryClient={injected}>
        <Probe />
      </AppProviders>,
    )
    expect(seenClient).toBe(injected)
  })
})
