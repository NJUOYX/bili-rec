/**
 * M30 DT：主题令牌（frontend-design.md §14.2/§14.3）。
 */
import { theme as antdTheme } from 'antd'

import {
  BRAND_PINK,
  BRAND_PINK_DARK,
  buildThemeConfig,
  darkThemeConfig,
  FONT_FAMILY,
  lightThemeConfig,
} from '../../../src/app/theme'

describe('app/theme', () => {
  it('亮色主题使用 B站粉主色与默认算法', () => {
    const config = lightThemeConfig()
    expect(config.algorithm).toBe(antdTheme.defaultAlgorithm)
    expect(config.token?.colorPrimary).toBe(BRAND_PINK)
    expect(config.token?.colorBgLayout).toBe('#F5F6F8')
    expect(config.token?.colorBgContainer).toBe('#FFFFFF')
  })

  it('暗色主题略提亮主色并叠加 darkAlgorithm', () => {
    const config = darkThemeConfig()
    expect(config.algorithm).toBe(antdTheme.darkAlgorithm)
    expect(config.token?.colorPrimary).toBe(BRAND_PINK_DARK)
    expect(config.token?.colorBgLayout).toBe('#0F0F0F')
    expect(config.token?.colorBgContainer).toBe('#1A1A1A')
  })

  it('共享令牌：大圆角/控件高度/字体栈/卡片圆角', () => {
    const config = lightThemeConfig()
    expect(config.token?.borderRadius).toBe(8)
    expect(config.token?.controlHeight).toBe(36)
    expect(config.token?.fontFamily).toBe(FONT_FAMILY)
    expect(config.components?.Card).toMatchObject({ borderRadiusLG: 12 })
  })

  it('buildThemeConfig 按解析主题分发', () => {
    expect(buildThemeConfig('light').token?.colorPrimary).toBe(BRAND_PINK)
    expect(buildThemeConfig('dark').token?.colorPrimary).toBe(BRAND_PINK_DARK)
  })
})
