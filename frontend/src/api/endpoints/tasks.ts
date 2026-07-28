/**
 * 任务域 hooks（frontend-design.md §5.1 第 3 步 / §6.1）。
 *
 * FM1 覆盖读接口 `GET /tasks/data`（分页 + select 筛选）；
 * 批量/单任务操作 mutation 随 M30 任务模块补充。
 */
import { useQuery } from '@tanstack/react-query'

import { api, call } from '../client'
import { queryKeys, type TasksDataQuery } from '../queryKeys'

/**
 * 任务列表分页数据：`{ total, page, size, tasks }`。
 * `query.select` 由任务筛选器映射（all/living/recording/...，§4）。
 */
export function useTasksData(query: TasksDataQuery = {}) {
  return useQuery({
    queryKey: queryKeys.tasks(query),
    queryFn: () =>
      call(() => api.GET('/api/v1/tasks/data', { params: { query } })),
  })
}
