/**
 * 数值格式化纯函数（frontend-design.md §10.1「纯逻辑」）。
 *
 * 供任务卡片/详情/Dashboard 展示速率、体积、时长与进度；
 * 全部为无副作用纯函数，便于确定性单测。
 */

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const

/** 字节数 → 人类可读体积（1024 进制，保留 1 位小数，B 级取整）。 */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  const text = unit === 0 ? String(Math.round(value)) : value.toFixed(1)
  return `${text} ${BYTE_UNITS[unit]}`
}

/** 字节速率 → 人类可读速率（如 `1.5 MB/s`）。 */
export function formatRate(bytesPerSecond: number): string {
  return `${formatBytes(bytesPerSecond)}/s`
}

/** 秒数 → `HH:MM:SS`（负数/非法值按 0 处理）。 */
export function formatDuration(seconds: number): string {
  const total =
    Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(h)}:${pad(m)}:${pad(s)}`
}

/** 0..1 比例 → 0..100 整数百分比（越界裁剪，非法值归 0）。 */
export function toPercent(ratio: number): number {
  if (!Number.isFinite(ratio) || ratio <= 0) return 0
  if (ratio >= 1) return 100
  return Math.round(ratio * 100)
}
