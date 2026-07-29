/**
 * 设置域 hooks（frontend-design.md §6.1 / §8.1）。
 *
 * 覆盖全局设置与任务级设置（null 回退语义）读写。
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

/** 任务级设置（GET /settings/tasks/{room_id}）。 */
export function useTaskSettings(roomId: number) {
  return useQuery({
    queryKey: queryKeys.taskSettings(roomId),
    queryFn: () =>
      call(() =>
        api.GET('/api/v1/settings/tasks/{room_id}', {
          params: { path: { room_id: roomId } },
        }),
      ),
    enabled: Number.isFinite(roomId),
  })
}

/**
 * 更新任务级设置（PATCH /settings/tasks/{room_id}），成功后失效该任务设置缓存。
 * 契约缺口同 usePatchSettings，以 never 断言透传 body。
 */
export function usePatchTaskSettings(roomId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      call(() =>
        api.PATCH('/api/v1/settings/tasks/{room_id}', {
          params: { path: { room_id: roomId } },
          body: body as never,
        }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.taskSettings(roomId),
      })
    },
  })
}
