/**
 * 主题切换控件（frontend-design.md §14.3：三态循环 system→light→dark）。
 *
 * 图标：跟随系统（显示器）/ 太阳 / 月亮；点击按序循环并持久化
 * （由 stores/theme 负责 localStorage 写入）。
 */
import { DesktopOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons'
import { Button, Tooltip } from 'antd'

import { useThemeStore, type ThemeMode } from '../stores/theme'

/** 三态循环顺序。 */
export function nextThemeMode(mode: ThemeMode): ThemeMode {
  if (mode === 'system') return 'light'
  if (mode === 'light') return 'dark'
  return 'system'
}

const MODE_PRESENTATION: Record<
  ThemeMode,
  { icon: React.ReactNode; label: string }
> = {
  system: { icon: <DesktopOutlined />, label: '跟随系统' },
  light: { icon: <SunOutlined />, label: '亮色' },
  dark: { icon: <MoonOutlined />, label: '暗色' },
}

export function ThemeToggle() {
  const mode = useThemeStore((s) => s.mode)
  const setMode = useThemeStore((s) => s.setMode)
  const { icon, label } = MODE_PRESENTATION[mode]
  return (
    <Tooltip title={`主题：${label}`}>
      <Button
        type="text"
        aria-label={`主题：${label}`}
        data-testid="theme-toggle"
        icon={icon}
        onClick={() => setMode(nextThemeMode(mode))}
      />
    </Tooltip>
  )
}
