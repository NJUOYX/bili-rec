/**
 * Query Key 规范化工厂（frontend-design.md §6.1）。
 *
 * 全部服务端数据的缓存键集中于此，供领域 hooks 与 WS 事件→缓存失效
 * 映射（FM2，§7.4）共用，避免键形状漂移。
 */
import type { paths } from './schema'

/** GET /tasks/data 的查询参数类型（派生自契约，禁止手写）。 */
export type TasksDataQuery = NonNullable<
  paths['/api/v1/tasks/data']['get']['parameters']['query']
>

/** 任务详情各子资源（§6.1）。 */
export type TaskPart =
  'data' | 'param' | 'metadata' | 'profile' | 'videos' | 'danmakus'

export const queryKeys = {
  /** 任务列表：['tasks', {page,size,select}] */
  tasks: (query: TasksDataQuery = {}) => ['tasks', query] as const,
  /** 单任务子资源：['task', roomId, part] */
  task: (roomId: number, part: TaskPart) => ['task', roomId, part] as const,
  /** 全局设置：['settings'] */
  settings: () => ['settings'] as const,
  /** 任务级设置：['settings', 'task', roomId] */
  taskSettings: (roomId: number) => ['settings', 'task', roomId] as const,
  /** 应用状态/信息：['app', 'status'|'info'] */
  app: (part: 'status' | 'info') => ['app', part] as const,
  /** 最新版本：['update', 'latest'] */
  updateLatest: () => ['update', 'latest'] as const,
} as const
