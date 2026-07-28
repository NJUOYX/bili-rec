/**
 * M28 DT：Query Key 规范化工厂（frontend-design.md §6.1）。
 */
import { queryKeys } from '../../../src/api/queryKeys'

describe('queryKeys', () => {
  it('任务列表键携带序列化查询参数', () => {
    expect(queryKeys.tasks({ page: 2, size: 10, select: 'recording' })).toEqual(
      ['tasks', { page: 2, size: 10, select: 'recording' }],
    )
    expect(queryKeys.tasks()).toEqual(['tasks', {}])
  })

  it('单任务子资源键：[task, roomId, part]', () => {
    expect(queryKeys.task(23058, 'data')).toEqual(['task', 23058, 'data'])
    expect(queryKeys.task(23058, 'videos')).toEqual(['task', 23058, 'videos'])
  })

  it('设置键：全局与任务级', () => {
    expect(queryKeys.settings()).toEqual(['settings'])
    expect(queryKeys.taskSettings(23058)).toEqual(['settings', 'task', 23058])
  })

  it('应用与版本键', () => {
    expect(queryKeys.app('status')).toEqual(['app', 'status'])
    expect(queryKeys.app('info')).toEqual(['app', 'info'])
    expect(queryKeys.updateLatest()).toEqual(['update', 'latest'])
  })
})
