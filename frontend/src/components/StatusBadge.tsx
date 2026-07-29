/**
 * 状态徽章（frontend-design.md §8.2/§14.6：monitor/recorder/running_status
 * 三维状态，颜色语义化）。
 */
import { Tag } from 'antd'

import {
  RUNNING_STATUS_LABELS,
  type RunningStatus,
  type TaskStatusView,
} from '../lib/task'

/** 运行状态 → AntD Tag 颜色（语义化，录制中用品牌粉强调）。 */
export const RUNNING_STATUS_COLORS: Record<RunningStatus, string> = {
  stopped: 'default',
  waiting: 'gold',
  recording: 'pink',
  remuxing: 'blue',
  injecting: 'purple',
}

export interface StatusBadgeProps {
  status: Pick<
    TaskStatusView,
    'monitor_enabled' | 'recorder_enabled' | 'running_status'
  >
}

/** 三枚徽章：监控开关 / 录制器开关 / 运行态。 */
export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span data-testid="status-badge">
      <Tag color={status.monitor_enabled ? 'green' : 'default'}>
        {status.monitor_enabled ? '监控中' : '监控关'}
      </Tag>
      <Tag color={status.recorder_enabled ? 'cyan' : 'default'}>
        {status.recorder_enabled ? '录制器开' : '录制器关'}
      </Tag>
      <Tag color={RUNNING_STATUS_COLORS[status.running_status]}>
        {RUNNING_STATUS_LABELS[status.running_status]}
      </Tag>
    </span>
  )
}
