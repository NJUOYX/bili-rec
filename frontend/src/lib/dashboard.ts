/**
 * Dashboard 统计聚合（frontend-design.md §14.5）。
 *
 * 从任务列表视图派生概览统计与「录制中」快捷卡片数据源，
 * 纯函数便于确定性单测。
 */
import type { TaskDataView } from './task'

export interface TasksSummary {
  total: number
  recording: number
  monitoring: number
  totalDlRate: number
  totalRecRate: number
}

/** 汇总任务列表：录制中/监控中计数与总速率。 */
export function summarizeTasks(tasks: TaskDataView[]): TasksSummary {
  return tasks.reduce<TasksSummary>(
    (acc, task) => {
      const s = task.task_status
      acc.total += 1
      if (s.running_status === 'recording') acc.recording += 1
      if (s.monitor_enabled) acc.monitoring += 1
      acc.totalDlRate += s.dl_rate
      acc.totalRecRate += s.rec_rate
      return acc
    },
    { total: 0, recording: 0, monitoring: 0, totalDlRate: 0, totalRecRate: 0 },
  )
}

/** 提取「录制中」任务（供快捷卡片）。 */
export function recordingTasks(tasks: TaskDataView[]): TaskDataView[] {
  return tasks.filter((t) => t.task_status.running_status === 'recording')
}

/** 从 app/status 响应稳健提取磁盘使用比例（0..1）；无数据返回 null。 */
export function parseDiskUsage(raw: unknown): number | null {
  if (typeof raw !== 'object' || raw === null) return null
  const disk = (raw as Record<string, unknown>).disk_usage
  if (typeof disk !== 'object' || disk === null) return null
  const d = disk as Record<string, unknown>
  const total = typeof d.total === 'number' ? d.total : 0
  const used = typeof d.used === 'number' ? d.used : 0
  if (total <= 0) return null
  return Math.min(1, Math.max(0, used / total))
}
