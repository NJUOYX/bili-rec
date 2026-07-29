/**
 * Vitest 单测环境补丁。
 *
 * jsdom 缺少 `matchMedia` 与 `ResizeObserver`，而 Ant Design 的响应式
 * 观察器与 Tabs/Layout 等组件依赖二者；此处提供最小确定性桩
 * （frontend-design.md §10.3 确定性约束）。
 */
import { vi } from 'vitest'

if (typeof window !== 'undefined') {
  if (!window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  }

  if (!window.ResizeObserver) {
    window.ResizeObserver = class ResizeObserver {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
  }
}
