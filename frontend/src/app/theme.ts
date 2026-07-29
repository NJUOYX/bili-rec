/**
 * 主题令牌集中定义（frontend-design.md §14.2）。
 *
 * 在 Ant Design 5 的 design-token 架构上定制：B站粉品牌主色、更大圆角、
 * 柔和多层阴影、更充裕控件尺寸；暗色叠加 `theme.darkAlgorithm` 并略提亮主色。
 * 由 `providers.tsx` 的 ConfigProvider 注入（§14.3 双主题）。
 */
import { theme as antdTheme, type ThemeConfig } from 'antd'

/** Bilibili 标志性品牌粉（亮色主色）。 */
export const BRAND_PINK = '#FB7299'
/** 暗色下略提亮的主色。 */
export const BRAND_PINK_DARK = '#FF85AB'

/** 解析后的实际主题（§14.3 三态 mode → 二态呈现）。 */
export type ResolvedTheme = 'light' | 'dark'

/** 字体栈：现代无衬线（§14.2）。 */
export const FONT_FAMILY =
  'Inter, "PingFang SC", "HarmonyOS Sans", system-ui, sans-serif'

/** 亮/暗共享的 token 与组件级覆写。 */
function sharedConfig(): ThemeConfig {
  return {
    token: {
      borderRadius: 8,
      controlHeight: 36,
      fontFamily: FONT_FAMILY,
    },
    components: {
      Card: { borderRadiusLG: 12 },
      Layout: { headerBg: 'transparent' },
    },
  }
}

/** 亮色主题配置。 */
export function lightThemeConfig(): ThemeConfig {
  const base = sharedConfig()
  return {
    ...base,
    algorithm: antdTheme.defaultAlgorithm,
    token: {
      ...base.token,
      colorPrimary: BRAND_PINK,
      colorBgLayout: '#F5F6F8',
      colorBgContainer: '#FFFFFF',
      boxShadow:
        '0 1px 2px rgba(16, 24, 40, 0.04), 0 4px 12px rgba(16, 24, 40, 0.06)',
      boxShadowSecondary:
        '0 2px 4px rgba(16, 24, 40, 0.04), 0 8px 24px rgba(16, 24, 40, 0.10)',
    },
  }
}

/** 暗色主题配置（§14.3：叠加 darkAlgorithm）。 */
export function darkThemeConfig(): ThemeConfig {
  const base = sharedConfig()
  return {
    ...base,
    algorithm: antdTheme.darkAlgorithm,
    token: {
      ...base.token,
      colorPrimary: BRAND_PINK_DARK,
      colorBgLayout: '#0F0F0F',
      colorBgContainer: '#1A1A1A',
      // 暗色下阴影弱化处理
      boxShadow: '0 1px 2px rgba(0, 0, 0, 0.36)',
      boxShadowSecondary: '0 2px 8px rgba(0, 0, 0, 0.48)',
    },
  }
}

/** 按解析后的主题构建 ConfigProvider 配置。 */
export function buildThemeConfig(resolved: ResolvedTheme): ThemeConfig {
  return resolved === 'dark' ? darkThemeConfig() : lightThemeConfig()
}
