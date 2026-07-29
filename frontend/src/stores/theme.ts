/**
 * 主题 store（Zustand，frontend-design.md §6.2/§14.3）。
 *
 * 三态模式 `system` / `light` / `dark`：
 * - 模式持久化于 localStorage，运行态存本 store；
 * - `system` 态由 Provider 监听 `matchMedia('(prefers-color-scheme: dark)')`
 *   的 change 事件实时写入 `systemDark`（watchSystemTheme）；
 * - `resolvedTheme` 把三态折叠为亮/暗二态，供 `buildThemeConfig` 消费。
 */
import { create } from 'zustand'

import type { ResolvedTheme } from '../app/theme'

/** 用户可选的主题模式（§14.3）。 */
export type ThemeMode = 'system' | 'light' | 'dark'

/** localStorage 持久化键。 */
export const THEME_STORAGE_KEY = 'birec.theme-mode'

const THEME_MODES: readonly ThemeMode[] = ['system', 'light', 'dark']

function isThemeMode(value: unknown): value is ThemeMode {
  return (
    typeof value === 'string' &&
    (THEME_MODES as readonly string[]).includes(value)
  )
}

/** 从 localStorage 读取模式；缺失/非法时回退 `system`。 */
export function loadStoredMode(): ThemeMode {
  if (typeof window === 'undefined') return 'system'
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY)
    return isThemeMode(raw) ? raw : 'system'
  } catch {
    return 'system'
  }
}

/** 读取系统当前是否暗色（无 matchMedia 能力时视为亮色）。 */
export function readSystemDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

/** 三态模式 + 系统偏好 → 实际呈现主题。 */
export function resolvedTheme(
  mode: ThemeMode,
  systemDark: boolean,
): ResolvedTheme {
  if (mode === 'light') return 'light'
  if (mode === 'dark') return 'dark'
  return systemDark ? 'dark' : 'light'
}

export interface ThemeState {
  mode: ThemeMode
  systemDark: boolean
  setMode: (mode: ThemeMode) => void
  setSystemDark: (systemDark: boolean) => void
}

export const useThemeStore = create<ThemeState>()((set) => ({
  mode: loadStoredMode(),
  systemDark: readSystemDark(),
  setMode: (mode) => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, mode)
    } catch {
      // 存储不可用（隐私模式等）时仅保留运行态
    }
    set({ mode })
  },
  setSystemDark: (systemDark) => set({ systemDark }),
}))

/** 便捷选择器：订阅解析后的亮/暗主题。 */
export function selectResolved(
  state: Pick<ThemeState, 'mode' | 'systemDark'>,
): ResolvedTheme {
  return resolvedTheme(state.mode, state.systemDark)
}

/**
 * 监听系统主题变化并同步到 store（§14.3）。
 * 返回清理函数；无 matchMedia 能力时为 no-op。
 */
export function watchSystemTheme(): () => void {
  if (typeof window === 'undefined' || !window.matchMedia) {
    return () => {}
  }
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const onChange = (event: MediaQueryListEvent) =>
    useThemeStore.getState().setSystemDark(event.matches)
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}
