/**
 * 应用域 hooks（frontend-design.md §6.1 / §8 关于页）。
 *
 * FM1 覆盖读接口：应用状态与应用信息；restart/exit 等操作随 M32 补充。
 */
import { useQuery } from '@tanstack/react-query'

import { api, call } from '../client'
import { queryKeys } from '../queryKeys'

/** 应用状态（GET /app/status）：任务统计/磁盘空间等。 */
export function useAppStatus() {
  return useQuery({
    queryKey: queryKeys.app('status'),
    queryFn: () => call(() => api.GET('/api/v1/app/status')),
  })
}

/** 应用信息（GET /app/info）：名称/版本/pid 等。 */
export function useAppInfo() {
  return useQuery({
    queryKey: queryKeys.app('info'),
    queryFn: () => call(() => api.GET('/api/v1/app/info')),
  })
}
