/**
 * 速率迷你曲线（frontend-design.md §14.5：自绘 SVG，不引图表库，§15 决策）。
 *
 * 纯展示组件：输入采样序列，按序归一化绘制 polyline；
 * 空序列/全零渲染基线，保证确定性（无动画、无随机）。
 */

export interface RateSparklineProps {
  /** 采样值序列（旧→新）。 */
  values: number[]
  width?: number
  height?: number
  /** 线条颜色（缺省品牌粉）。 */
  stroke?: string
  /** 无障碍标签。 */
  label?: string
}

/** 把采样序列映射为 SVG polyline 坐标点（含边距，最大值归一化）。 */
export function toPolylinePoints(
  values: number[],
  width: number,
  height: number,
): string {
  const pad = 2
  const innerW = width - pad * 2
  const innerH = height - pad * 2
  if (values.length === 0) return ''
  if (values.length === 1) {
    return `${pad},${height - pad} ${width - pad},${height - pad}`
  }
  const max = Math.max(...values)
  const step = innerW / (values.length - 1)
  return values
    .map((v, i) => {
      const x = pad + i * step
      const y = max > 0 ? pad + innerH - (v / max) * innerH : height - pad
      return `${Math.round(x * 10) / 10},${Math.round(y * 10) / 10}`
    })
    .join(' ')
}

export function RateSparkline({
  values,
  width = 120,
  height = 32,
  stroke = '#FB7299',
  label = '速率曲线',
}: RateSparklineProps) {
  return (
    <svg
      role="img"
      aria-label={label}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      data-testid="rate-sparkline"
    >
      <polyline
        points={toPolylinePoints(values, width, height)}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}
