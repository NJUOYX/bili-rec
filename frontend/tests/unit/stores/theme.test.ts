/**
 * M30 DT：主题 store（frontend-design.md §6.2/§14.3）。
 */
import { act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  loadStoredMode,
  readSystemDark,
  resolvedTheme,
  selectResolved,
  THEME_STORAGE_KEY,
  useThemeStore,
  watchSystemTheme,
} from '../../../src/stores/theme'

type MediaListener = (event: { matches: boolean }) => void

/** 安装可控的 matchMedia 桩，返回触发 change 的函数。 */
function installMatchMedia(initialDark: boolean) {
  let listener: MediaListener | undefined
  const media = {
    matches: initialDark,
    media: '(prefers-color-scheme: dark)',
    addEventListener: vi.fn((_name: string, fn: MediaListener) => {
      listener = fn
    }),
    removeEventListener: vi.fn(() => {
      listener = undefined
    }),
  }
  const matchMedia = vi.fn(() => media)
  vi.stubGlobal('matchMedia', matchMedia)
  window.matchMedia = matchMedia as unknown as typeof window.matchMedia
  return {
    fireChange(matches: boolean) {
      listener?.({ matches })
    },
    removeEventListener: media.removeEventListener,
  }
}

describe('stores/theme', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useThemeStore.setState({ mode: 'system', systemDark: false })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('resolvedTheme', () => {
    it('手动模式优先于系统偏好', () => {
      expect(resolvedTheme('light', true)).toBe('light')
      expect(resolvedTheme('dark', false)).toBe('dark')
    })

    it('system 模式跟随系统偏好', () => {
      expect(resolvedTheme('system', true)).toBe('dark')
      expect(resolvedTheme('system', false)).toBe('light')
    })
  })

  describe('loadStoredMode', () => {
    it('读取合法存储值', () => {
      window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')
      expect(loadStoredMode()).toBe('dark')
    })

    it('缺失或非法值回退 system', () => {
      expect(loadStoredMode()).toBe('system')
      window.localStorage.setItem(THEME_STORAGE_KEY, 'neon')
      expect(loadStoredMode()).toBe('system')
    })
  })

  describe('readSystemDark', () => {
    it('matchMedia 命中暗色时返回 true', () => {
      installMatchMedia(true)
      expect(readSystemDark()).toBe(true)
    })

    it('无 matchMedia 能力时视为亮色', () => {
      vi.stubGlobal('matchMedia', undefined)
      // jsdom window.matchMedia 已被 setup.ts 注入，这里直接删除模拟缺失
      delete (window as { matchMedia?: unknown }).matchMedia
      expect(readSystemDark()).toBe(false)
    })
  })

  describe('setMode', () => {
    it('更新运行态并持久化', () => {
      act(() => useThemeStore.getState().setMode('dark'))
      expect(useThemeStore.getState().mode).toBe('dark')
      expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    })

    it('存储抛错时仍更新运行态', () => {
      const spy = vi
        .spyOn(Storage.prototype, 'setItem')
        .mockImplementation(() => {
          throw new Error('quota')
        })
      act(() => useThemeStore.getState().setMode('light'))
      expect(useThemeStore.getState().mode).toBe('light')
      spy.mockRestore()
    })
  })

  describe('selectResolved', () => {
    it('聚合 mode 与 systemDark', () => {
      expect(selectResolved({ mode: 'system', systemDark: true })).toBe('dark')
      expect(selectResolved({ mode: 'light', systemDark: true })).toBe('light')
    })
  })

  describe('watchSystemTheme', () => {
    it('系统主题变化时写入 store，取消订阅后不再响应', () => {
      const media = installMatchMedia(false)
      const stop = watchSystemTheme()

      act(() => media.fireChange(true))
      expect(useThemeStore.getState().systemDark).toBe(true)

      stop()
      expect(media.removeEventListener).toHaveBeenCalled()
      act(() => media.fireChange(false))
      expect(useThemeStore.getState().systemDark).toBe(true)
    })

    it('无 matchMedia 能力时返回 no-op 清理函数', () => {
      delete (window as { matchMedia?: unknown }).matchMedia
      const stop = watchSystemTheme()
      expect(() => stop()).not.toThrow()
    })
  })
})
