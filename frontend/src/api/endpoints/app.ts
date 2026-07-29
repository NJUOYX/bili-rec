/**
 * 应用域 hooks（frontend-design.md §6.1 / §8 关于页）。
 *
 * 覆盖读接口（状态/信息/最新版本）与操作（重启/退出/目录校验）。
 */
import { useMutation, useQuery } from '@tanstack/react-query'

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

/** 最新版本（GET /update/version/latest）：{ version, current }。 */
export function useLatestVersion() {
  return useQuery({
    queryKey: queryKeys.updateLatest(),
    queryFn: () => call(() => api.GET('/api/v1/update/version/latest')),
    retry: false,
  })
}

/** 重启应用（POST /app/restart）。 */
export function useRestartApp() {
  return useMutation({
    mutationFn: () => call(() => api.POST('/api/v1/app/restart')),
  })
}

/** 退出应用（POST /app/exit）。 */
export function useExitApp() {
  return useMutation({
    mutationFn: () => call(() => api.POST('/api/v1/app/exit')),
  })
}

/** 目录校验（POST /validation/dir）：body { path }。 */
export function useValidateDir() {
  return useMutation({
    mutationFn: (path: string) =>
      call(() =>
        api.POST('/api/v1/validation/dir', { body: { path } as never }),
      ),
  })
}
