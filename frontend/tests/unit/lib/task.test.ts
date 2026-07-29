import {
  filterToSelect,
  parseTaskData,
  parseTaskStatus,
  parseTasksPage,
  RUNNING_STATUS_LABELS,
  TASK_FILTER_OPTIONS,
} from '../../../src/lib/task'
import { makeTaskDataRaw } from '../helpers/fixtures'

describe('parseTaskStatus', () => {
  it('完整载荷逐字段解析', () => {
    const status = parseTaskStatus(makeTaskDataRaw().task_status)
    expect(status.monitor_enabled).toBe(true)
    expect(status.running_status).toBe('recording')
    expect(status.dl_rate).toBe(512 * 1024)
    expect(status.postprocessing_progress).toBe(0.42)
  })

  it('非对象/缺字段回退后端默认值（降级）', () => {
    const status = parseTaskStatus(undefined)
    expect(status.monitor_enabled).toBe(false)
    expect(status.recorder_enabled).toBe(false)
    expect(status.running_status).toBe('stopped')
    expect(status.dl_rate).toBe(0)
    expect(status.recording_path).toBe('')
  })

  it('未知 running_status 回退 stopped', () => {
    const status = parseTaskStatus({ running_status: 'exploded' })
    expect(status.running_status).toBe('stopped')
  })
})

describe('parseTaskData', () => {
  it('完整载荷解析', () => {
    const td = parseTaskData(makeTaskDataRaw())
    expect(td).not.toBeNull()
    expect(td!.room_id).toBe(23058)
    expect(td!.user_name).toBe('3号直播间')
    expect(td!.live_status).toBe(true)
    expect(td!.task_status.running_status).toBe('recording')
  })

  it('缺 room_id/非对象 → null', () => {
    expect(parseTaskData({})).toBeNull()
    expect(parseTaskData(null)).toBeNull()
    expect(parseTaskData('x')).toBeNull()
    expect(parseTaskData({ room_id: '23058' })).toBeNull()
  })

  it('缺展示字段做降级（空串/false）', () => {
    const td = parseTaskData({ room_id: 1 })
    expect(td!.user_name).toBe('')
    expect(td!.room_title).toBe('')
    expect(td!.live_status).toBe(false)
    expect(td!.task_status.running_status).toBe('stopped')
  })
})

describe('parseTasksPage', () => {
  it('解析分页外壳与条目', () => {
    const page = parseTasksPage({
      total: 2,
      page: 1,
      size: 20,
      tasks: [makeTaskDataRaw(), makeTaskDataRaw({ room_id: 9 })],
    })
    expect(page.total).toBe(2)
    expect(page.tasks).toHaveLength(2)
    expect(page.tasks[1].room_id).toBe(9)
  })

  it('畸形条目静默丢弃', () => {
    const page = parseTasksPage({
      total: 3,
      tasks: [makeTaskDataRaw(), null, { no_room: true }],
    })
    expect(page.tasks).toHaveLength(1)
  })

  it('非对象/缺 tasks 整体降级为空页', () => {
    expect(parseTasksPage(undefined).tasks).toEqual([])
    expect(parseTasksPage({}).total).toBe(0)
    expect(parseTasksPage({}).page).toBe(1)
    expect(parseTasksPage({}).size).toBe(20)
  })
})

describe('筛选器映射（§10.1 筛选器→select）', () => {
  it('all 不传 select', () => {
    expect(filterToSelect('all')).toBeUndefined()
  })

  it('其余筛选值透传（与后端 _matches_filter 对齐）', () => {
    expect(filterToSelect('living')).toBe('living')
    expect(filterToSelect('recording')).toBe('recording')
    expect(filterToSelect('monitor_disabled')).toBe('monitor_disabled')
  })

  it('选项覆盖后端全部 select 维度', () => {
    const values = TASK_FILTER_OPTIONS.map((o) => o.value)
    expect(values).toEqual([
      'all',
      'living',
      'preparing',
      'recording',
      'waiting',
      'stopped',
      'remuxing',
      'injecting',
      'monitor_enabled',
      'monitor_disabled',
      'recorder_enabled',
      'recorder_disabled',
    ])
  })
})

describe('RUNNING_STATUS_LABELS', () => {
  it('覆盖全部运行状态', () => {
    expect(Object.keys(RUNNING_STATUS_LABELS).sort()).toEqual(
      ['injecting', 'recording', 'remuxing', 'stopped', 'waiting'].sort(),
    )
  })
})
