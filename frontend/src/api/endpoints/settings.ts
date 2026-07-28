/**
 * 设置域 hooks（frontend-design.md §6.1 / §8.1）。
 *
 * FM1 覆盖全局设置读写；任务级设置（null 回退语义）随 M31 设置模块补充。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, call } from '../client'
import { queryKeys } from '../queryKeys'

/** 全局设置（GET /settings）。 */
export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings(),
    queryFn: () => call(() => api.GET('/api/v1/settings')),
  })
}

/**
 * 更新全局设置（PATCH /settings），成功后失效 ['settings'] 缓存。
 *
 * 契约缺口：后端手工解析 JSON，openapi.json 未声明 requestBody
 * （生成类型为 `requestBody?: never`），此处以 never 断言透传 JSON
 * body（运行时由 openapi-fetch 正常序列化）。契约补全后移除断言。
 */
export function usePatchSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      call(() => api.PATCH('/api/v1/settings', { body: body as never })),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings() })
    },
  })
}
