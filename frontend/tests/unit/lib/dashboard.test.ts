/**
 * M30 DT：Dashboard 统计聚合纯函数（§14.5）。
 */
import { describe, expect, it } from 'vitest'

import {
  parseDiskUsage,
  recordingTasks,
  summarizeTasks,
} from '../../../src/lib/dashboard'
import { parseTaskData, type TaskDataView } from '../../../src/lib/task'
import { makeTaskDataRaw } from '../helpers/fixtures'

function task(
  overrides: Record<string, unknown> = {},
  statusOverrides: Record<string, unknown> = {},
): TaskDataView {
  const parsed = parseTaskData(makeTaskDataRaw(overrides, statusOverrides))
  if (!parsed) throw new Error('fixture parse failed')
  return parsed
}

describe('summarizeTasks', () => {
  it('空列表 → 全零', () => {
    expect(summarizeTasks([])).toEqual({
      total: 0,
      recording: 0,
      monitoring: 0,
      totalDlRate: 0,
      totalRecRate: 0,
    })
  })

  it('统计录制中/监控中计数与总速率', () => {
    const tasks = [
      task({ room_id: 1 }, { running_status: 'recording', dl_rate: 100 }),
      task(
        { room_id: 2 },
        { running_status: 'waiting', monitor_enabled: true, dl_rate: 50 },
      ),
      task(
        { room_id: 3 },
        { running_status: 'stopped', monitor_enabled: false, dl_rate: 0 },
      ),
    ]
    const s = summarizeTasks(tasks)
    expect(s.total).toBe(3)
    expect(s.recording).toBe(1)
    expect(s.monitoring).toBe(2)
    expect(s.totalDlRate).toBe(150)
  })
})

describe('recordingTasks', () => {
  it('仅保留 recording 状态', () => {
    const tasks = [
      task({ room_id: 1 }, { running_status: 'recording' }),
      task({ room_id: 2 }, { running_status: 'waiting' }),
    ]
    expect(recordingTasks(tasks).map((t) => t.room_id)).toEqual([1])
  })
})

describe('parseDiskUsage', () => {
  it('无数据/畸形 → null', () => {
    expect(parseDiskUsage(null)).toBeNull()
    expect(parseDiskUsage({})).toBeNull()
    expect(parseDiskUsage({ disk_usage: { total: 0, used: 0 } })).toBeNull()
  })

  it('计算并裁剪比例', () => {
    expect(parseDiskUsage({ disk_usage: { total: 100, used: 25 } })).toBe(0.25)
    expect(parseDiskUsage({ disk_usage: { total: 100, used: 250 } })).toBe(1)
  })
})
