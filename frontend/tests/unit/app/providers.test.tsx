/**
 * M28/M30 DT：全局 Provider 组合（frontend-design.md §3/§9/§14.2/§14.3）。
 */
import { QueryClient, useMutation, useQueryClient } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { theme as antdTheme } from 'antd'

import { AppProviders } from '../../../src/app/providers'
import { describeApiError } from '../../../src/lib/errors'
import { ApiError } from '../../../src/api/client'
import { THEME_STORAGE_KEY, useThemeStore } from '../../../src/stores/theme'
import { BRAND_PINK } from '../../../src/app/theme'

let seenClient: QueryClient | undefined

function Probe() {
  seenClient = useQueryClient()
  return <p>probe-ok</p>
}

/** 读取 ConfigProvider 注入的主色，断言主题生效。 */
function ColorProbe() {
  const { token } = antdTheme.useToken()
  return <p data-testid="primary-color">{String(token.colorPrimary)}</p>
}

function FailingMutation() {
  const mutation = useMutation({
    mutationFn: () => Promise.reject(new ApiError(400, '房间号不存在')),
  })
  return (
    <button type="button" onClick={() => mutation.mutate()}>
      trigger
    </button>
  )
}

describe('AppProviders', () => {
  beforeEach(() => {
    seenClient = undefined
    window.localStorage.clear()
    useThemeStore.setState({ mode: 'system', systemDark: false })
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

  it('注入亮色主题令牌（B站粉主色）', () => {
    render(
      <AppProviders>
        <ColorProbe />
      </AppProviders>,
    )
    // antd 将种子色归一化为小写
    expect(screen.getByTestId('primary-color').textContent).toBe(
      BRAND_PINK.toLowerCase(),
    )
  })

  it('切换暗色模式后主色随之切换', () => {
    render(
      <AppProviders>
        <ColorProbe />
      </AppProviders>,
    )
    act(() => useThemeStore.getState().setMode('dark'))
    // 暗色算法对种子主色做色板派生，断言主色已切换（不等于亮色种子）
    expect(screen.getByTestId('primary-color').textContent).not.toBe(BRAND_PINK)
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
  })

  it('mutation 错误经全局通知呈现（§9）', async () => {
    render(
      <AppProviders queryClient={new QueryClient()}>
        <FailingMutation />
      </AppProviders>,
    )
    fireEvent.click(screen.getByText('trigger'))
    expect(await screen.findByText('业务错误')).toBeTruthy()
    expect(await screen.findByText('房间号不存在')).toBeTruthy()
  })
})

describe('describeApiError', () => {
  it('ApiError 按分类映射标题', () => {
    expect(describeApiError(new ApiError(404, 'missing'))).toEqual({
      message: '资源不存在',
      description: 'missing',
    })
    expect(describeApiError(new ApiError(403, 'denied')).message).toBe(
      '操作被禁止',
    )
    expect(describeApiError(new ApiError(-1, 'net', 'network')).message).toBe(
      '网络错误',
    )
  })

  it('普通错误与未知值降级为通用文案', () => {
    expect(describeApiError(new Error('boom'))).toEqual({
      message: '未知错误',
      description: 'boom',
    })
    expect(describeApiError('raw').description).toBe('raw')
  })
})
