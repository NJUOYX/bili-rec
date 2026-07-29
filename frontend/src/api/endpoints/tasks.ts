/**
 * 任务域 hooks（frontend-design.md §5.1 第 3 步 / §6.1 / §8）。
 *
 * 读接口：任务列表分页 + 单任务六类子资源（data/param/metadata/profile/
 * videos/danmakus）；写接口：添加/删除、单任务与批量的启停、录制器开关、
 * 信息刷新。全部经 `call` 拆包 ResponseMessage（§4），mutation 成功后按
 * queryKeys 失效相关缓存（§6.3）。
 *
 * 手动切割（cut）已在后端功能范围决策中移除，无对应端点。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, call } from '../client'
import { queryKeys, type TaskPart, type TasksDataQuery } from '../queryKeys'

/** 列表/详情的实时兜底轮询间隔（毫秒）：速率等运行态字段无 WS 推送。 */
export const TASKS_REFETCH_INTERVAL = 2_000

export interface TasksQueryOptions {
  /** 覆盖轮询间隔；false 关闭轮询（测试用）。 */
  refetchInterval?: number | false
}

/**
 * 任务列表分页数据：`{ total, page, size, tasks }`。
 * `query.select` 由任务筛选器映射（all/living/recording/...，§4）；
 * 运行态速率字段无事件推送，默认以短轮询刷新（§9 兜底策略）。
 */
export function useTasksData(
  query: TasksDataQuery = {},
  options: TasksQueryOptions = {},
) {
  return useQuery({
    queryKey: queryKeys.tasks(query),
    queryFn: () =>
      call(() => api.GET('/api/v1/tasks/data', { params: { query } })),
    refetchInterval: options.refetchInterval ?? TASKS_REFETCH_INTERVAL,
  })
}

/** 单任务子资源 GET 路径映射（六类，§8）。 */
const TASK_PART_PATHS = {
  data: '/api/v1/tasks/{room_id}/data',
  param: '/api/v1/tasks/{room_id}/param',
  metadata: '/api/v1/tasks/{room_id}/metadata',
  profile: '/api/v1/tasks/{room_id}/profile',
  videos: '/api/v1/tasks/{room_id}/videos',
  danmakus: '/api/v1/tasks/{room_id}/danmakus',
} as const satisfies Record<TaskPart, string>

function useTaskPart(
  roomId: number,
  part: TaskPart,
  options: TasksQueryOptions = {},
) {
  return useQuery({
    queryKey: queryKeys.task(roomId, part),
    queryFn: () =>
      call(() =>
        api.GET(TASK_PART_PATHS[part], {
          params: { path: { room_id: roomId } },
        }),
      ),
    refetchInterval: options.refetchInterval ?? false,
  })
}

/** 单任务状态数据（GET /tasks/{room_id}/data），默认短轮询刷新运行态。 */
export function useTaskData(roomId: number, options: TasksQueryOptions = {}) {
  return useTaskPart(roomId, 'data', {
    refetchInterval: options.refetchInterval ?? TASKS_REFETCH_INTERVAL,
  })
}

/** 任务参数快照（GET /tasks/{room_id}/param）。 */
export function useTaskParam(roomId: number) {
  return useTaskPart(roomId, 'param')
}

/** 录制元数据（GET /tasks/{room_id}/metadata）。 */
export function useTaskMetadata(roomId: number) {
  return useTaskPart(roomId, 'metadata')
}

/** 流 ffprobe Profile（GET /tasks/{room_id}/profile）。 */
export function useTaskProfile(roomId: number) {
  return useTaskPart(roomId, 'profile')
}

/** 视频文件明细（GET /tasks/{room_id}/videos）。 */
export function useTaskVideos(roomId: number) {
  return useTaskPart(roomId, 'videos')
}

/** 弹幕文件明细（GET /tasks/{room_id}/danmakus）。 */
export function useTaskDanmakus(roomId: number) {
  return useTaskPart(roomId, 'danmakus')
}

/** mutation 成功后的统一失效：列表前缀 +（可选）单任务全部子资源。 */
function useInvalidateTasks() {
  const queryClient = useQueryClient()
  return async (roomId?: number) => {
    await queryClient.invalidateQueries({ queryKey: ['tasks'] })
    if (roomId !== undefined) {
      await queryClient.invalidateQueries({ queryKey: ['task', roomId] })
    }
  }
}

/**
 * 添加任务（POST /tasks/{room_id}，支持短号，返回真实房号）。
 *
 * 契约缺口：后端未在签名中声明 room_id 路径参数（以 body.room_id 为准），
 * openapi.json 生成 `path?: never`；运行时 openapi-fetch 仍按 params.path
 * 替换 URL 占位符，故此处以 never 断言透传路径参数。契约补全后移除断言。
 */
export function useAddTask() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (roomId: number) =>
      call(() =>
        api.POST('/api/v1/tasks/{room_id}', {
          params: { path: { room_id: roomId } } as never,
          body: { room_id: roomId, auto_enable: true },
        }),
      ),
    onSuccess: () => invalidate(),
  })
}

/** 启动单任务监控（POST /tasks/{room_id}/start）。 */
export function useStartTask() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (roomId: number) =>
      call(() =>
        api.POST('/api/v1/tasks/{room_id}/start', {
          params: { path: { room_id: roomId } },
        }),
      ),
    onSuccess: (_data, roomId) => invalidate(roomId),
  })
}

/** 停止单任务监控（POST /tasks/{room_id}/stop）。 */
export function useStopTask() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (roomId: number) =>
      call(() =>
        api.POST('/api/v1/tasks/{room_id}/stop', {
          params: { path: { room_id: roomId } },
        }),
      ),
    onSuccess: (_data, roomId) => invalidate(roomId),
  })
}

/** 单任务录制器开关（POST /tasks/{room_id}/recorder/enable|disable）。 */
export function useSetTaskRecorder() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: ({ roomId, enabled }: { roomId: number; enabled: boolean }) =>
      call(() =>
        enabled
          ? api.POST('/api/v1/tasks/{room_id}/recorder/enable', {
              params: { path: { room_id: roomId } },
            })
          : api.POST('/api/v1/tasks/{room_id}/recorder/disable', {
              params: { path: { room_id: roomId } },
            }),
      ),
    onSuccess: (_data, { roomId }) => invalidate(roomId),
  })
}

/** 刷新单任务信息（POST /tasks/{room_id}/info）。 */
export function useRefreshTaskInfo() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (roomId: number) =>
      call(() =>
        api.POST('/api/v1/tasks/{room_id}/info', {
          params: { path: { room_id: roomId } },
        }),
      ),
    onSuccess: (_data, roomId) => invalidate(roomId),
  })
}

/** 删除单任务（DELETE /tasks/{room_id}）。 */
export function useDeleteTask() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (roomId: number) =>
      call(() =>
        api.DELETE('/api/v1/tasks/{room_id}', {
          params: { path: { room_id: roomId } },
        }),
      ),
    onSuccess: (_data, roomId) => invalidate(roomId),
  })
}

/** 批量启动监控（POST /tasks/start；空数组=全部）。 */
export function useBatchStart() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (roomIds: number[] = []) =>
      call(() =>
        api.POST('/api/v1/tasks/start', { body: { room_ids: roomIds } }),
      ),
    onSuccess: () => invalidate(),
  })
}

/** 批量停止监控（POST /tasks/stop；空数组=全部）。 */
export function useBatchStop() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (roomIds: number[] = []) =>
      call(() =>
        api.POST('/api/v1/tasks/stop', {
          body: { room_ids: roomIds, force: false, background: false },
        }),
      ),
    onSuccess: () => invalidate(),
  })
}

/** 批量录制器开关（POST /tasks/recorder/enable|disable；空数组=全部）。 */
export function useBatchSetRecorder() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: ({
      roomIds = [],
      enabled,
    }: {
      roomIds?: number[]
      enabled: boolean
    }) =>
      call(() =>
        enabled
          ? api.POST('/api/v1/tasks/recorder/enable', {
              body: { room_ids: roomIds },
            })
          : api.POST('/api/v1/tasks/recorder/disable', {
              body: { room_ids: roomIds },
            }),
      ),
    onSuccess: () => invalidate(),
  })
}

/** 批量删除任务（DELETE /tasks）。 */
export function useDeleteTasks() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (roomIds: number[]) =>
      call(() => api.DELETE('/api/v1/tasks', { body: { room_ids: roomIds } })),
    onSuccess: () => invalidate(),
  })
}

/** 批量刷新任务信息（POST /tasks/info）。 */
export function useBatchRefreshInfo() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: () => call(() => api.POST('/api/v1/tasks/info')),
    onSuccess: () => invalidate(),
  })
}
