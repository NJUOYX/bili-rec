/**
 * 任务数据视图模型（frontend-design.md §14.6：展示字段以 `/tasks/data` 的
 * `TaskData` 为准，缺失字段做降级）。
 *
 * 后端契约（openapi.json）对任务响应仅声明为无类型 object，实际运行时形态
 * 由 `task/__init__.py::TaskData`（dataclass asdict + RunningStatus 枚举值）
 * 决定：扁平结构 `{room_id, user_name, room_title, area, parent_area,
 * live_status, task_status}`。此处提供运行时解析守卫：
 * - 缺失字段回退后端 dataclass 默认值（降级呈现，不崩溃）；
 * - 无 `room_id` 的畸形条目返回 null（调用侧丢弃）；
 * - 手动切割（cut）已在后端功能范围决策中移除，无对应端点/字段。
 */

/** 运行状态机（task/__init__.py::RunningStatus）。 */
export const RUNNING_STATUSES = [
  'stopped',
  'waiting',
  'recording',
  'remuxing',
  'injecting',
] as const

export type RunningStatus = (typeof RUNNING_STATUSES)[number]

/** 运行状态 → 中文标签。 */
export const RUNNING_STATUS_LABELS: Record<RunningStatus, string> = {
  stopped: '已停止',
  waiting: '等待开播',
  recording: '录制中',
  remuxing: '混流中',
  injecting: '注入中',
}

/** TaskStatus 的运行时视图（字段与后端 dataclass 对齐）。 */
export interface TaskStatusView {
  monitor_enabled: boolean
  recorder_enabled: boolean
  running_status: RunningStatus
  stream_url: string
  stream_host: string
  dl_total: number
  dl_rate: number
  rec_elapsed: number
  rec_total: number
  rec_rate: number
  danmu_total: number
  danmu_rate: number
  real_stream_format: string
  real_quality_number: number
  recording_path: string
  postprocessor_status: string
  postprocessing_path: string
  postprocessing_progress: number
}

/** TaskData 的运行时视图。 */
export interface TaskDataView {
  room_id: number
  user_name: string
  room_title: string
  area: string
  parent_area: string
  cover_url: string
  live_status: boolean
  task_status: TaskStatusView
}

/** GET /tasks/data 的分页视图。 */
export interface TasksPageView {
  total: number
  page: number
  size: number
  tasks: TaskDataView[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function str(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function num(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function bool(value: unknown, fallback = false): boolean {
  return typeof value === 'boolean' ? value : fallback
}

function runningStatus(value: unknown): RunningStatus {
  return (RUNNING_STATUSES as readonly string[]).includes(value as string)
    ? (value as RunningStatus)
    : 'stopped'
}

/** 解析 task_status；非对象时整体回退默认值（降级）。 */
export function parseTaskStatus(raw: unknown): TaskStatusView {
  const r = isRecord(raw) ? raw : {}
  return {
    monitor_enabled: bool(r.monitor_enabled),
    recorder_enabled: bool(r.recorder_enabled),
    running_status: runningStatus(r.running_status),
    stream_url: str(r.stream_url),
    stream_host: str(r.stream_host),
    dl_total: num(r.dl_total),
    dl_rate: num(r.dl_rate),
    rec_elapsed: num(r.rec_elapsed),
    rec_total: num(r.rec_total),
    rec_rate: num(r.rec_rate),
    danmu_total: num(r.danmu_total),
    danmu_rate: num(r.danmu_rate),
    real_stream_format: str(r.real_stream_format),
    real_quality_number: num(r.real_quality_number),
    recording_path: str(r.recording_path),
    postprocessor_status: str(r.postprocessor_status),
    postprocessing_path: str(r.postprocessing_path),
    postprocessing_progress: num(r.postprocessing_progress),
  }
}

/** 解析单条 TaskData；缺 `room_id` 视为畸形返回 null。 */
export function parseTaskData(raw: unknown): TaskDataView | null {
  if (!isRecord(raw) || typeof raw.room_id !== 'number') return null
  return {
    room_id: raw.room_id,
    user_name: str(raw.user_name),
    room_title: str(raw.room_title),
    area: str(raw.area),
    parent_area: str(raw.parent_area),
    cover_url: str(raw.cover_url),
    live_status: bool(raw.live_status),
    task_status: parseTaskStatus(raw.task_status),
  }
}

/** 解析分页响应 `{total, page, size, tasks}`；畸形条目静默丢弃。 */
export function parseTasksPage(raw: unknown): TasksPageView {
  const r = isRecord(raw) ? raw : {}
  const tasks = Array.isArray(r.tasks)
    ? r.tasks.map(parseTaskData).filter((t): t is TaskDataView => t !== null)
    : []
  return {
    total: num(r.total, tasks.length),
    page: num(r.page, 1),
    size: num(r.size, 20),
    tasks,
  }
}

/** 任务筛选器选项（后端 `_matches_filter` 支持的 select 值，§8）。 */
export const TASK_FILTER_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'living', label: '直播中' },
  { value: 'preparing', label: '未开播' },
  { value: 'recording', label: '录制中' },
  { value: 'waiting', label: '等待开播' },
  { value: 'stopped', label: '已停止' },
  { value: 'remuxing', label: '混流中' },
  { value: 'injecting', label: '注入中' },
  { value: 'monitor_enabled', label: '监控已启用' },
  { value: 'monitor_disabled', label: '监控已停用' },
  { value: 'recorder_enabled', label: '录制器已启用' },
  { value: 'recorder_disabled', label: '录制器已停用' },
] as const

export type TaskFilter = (typeof TASK_FILTER_OPTIONS)[number]['value']

/** 筛选器 → `GET /tasks/data` 的 select 参数（`all` 不传参）。 */
export function filterToSelect(filter: TaskFilter): string | undefined {
  return filter === 'all' ? undefined : filter
}

/** 文件明细（`VideoFileDetail` / `DanmakuFileDetail`）的运行时视图。 */
export interface FileDetailView {
  path: string
  size: number
  status: string
}

/** 文件状态 → 中文标签（task/__init__.py::FileStatus）。 */
export const FILE_STATUS_LABELS: Record<string, string> = {
  recording: '录制中',
  remuxing: '混流中',
  injecting: '注入中',
  completed: '已完成',
  missing: '文件缺失',
  unknown: '未知',
}

/**
 * 解析 `{videos: [...]}` / `{danmakus: [...]}` 响应为文件明细列表。
 *
 * 与 `parseTaskData` 同样的降级策略：非数组或畸形条目直接忽略，
 * 单条缺字段回退后端 dataclass 默认值。
 */
export function parseFileDetails(data: unknown, key: string): FileDetailView[] {
  if (!isRecord(data)) return []
  const items = data[key]
  if (!Array.isArray(items)) return []
  return items.filter(isRecord).map((item) => ({
    path: str(item.path),
    size: num(item.size),
    status: str(item.status, 'unknown'),
  }))
}

/** 任务参数/元数据字段 → 中文标签（未知字段回退原始键名）。 */
export const TASK_FIELD_LABELS: Record<string, string> = {
  room_id: '房间号',
  enable_monitor: '监控',
  enable_recorder: '录制器',
  user_name: '主播',
  room_title: '标题',
  area: '分区',
  parent_area: '父分区',
  live_start_time: '开播时间',
  cover_url: '封面',
}

/** 键值对视图（供 Descriptions 渲染）。 */
export interface FieldEntry {
  key: string
  label: string
  value: unknown
}

/**
 * 将无类型的子资源响应摊平为有序键值对。
 *
 * 契约只声明 object（openapi.json），因此按响应实际返回的键渲染，而不是写死
 * 字段列表：后端新增字段会自动出现，缺失字段自动消失。
 */
export function toFieldEntries(data: unknown): FieldEntry[] {
  if (!isRecord(data)) return []
  return Object.entries(data)
    .filter(([, value]) => typeof value !== 'object' || value === null)
    .map(([key, value]) => ({
      key,
      label: TASK_FIELD_LABELS[key] ?? key,
      value,
    }))
}
