/**
 * 后处理进度条（frontend-design.md §8.2/§14.6）。
 */
import { Progress } from 'antd'

import { toPercent } from '../lib/format'

export interface ProgressBarProps {
  /** 进度比例（0..1，后端 postprocessing_progress）。 */
  ratio: number
  /** 展示标签（如「混流中」）。 */
  label?: string
}

/** AntD Progress 包装：0..1 比例 → 百分比，附可选标签。 */
export function ProgressBar({ ratio, label }: ProgressBarProps) {
  return (
    <div data-testid="progress-bar">
      {label ? (
        <span style={{ fontSize: 12, opacity: 0.65 }}>{label}</span>
      ) : null}
      <Progress percent={toPercent(ratio)} size="small" />
    </div>
  )
}
