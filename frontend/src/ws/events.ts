/**
 * WebSocket 消息类型与解析守卫（frontend-design.md §7.1/§7.2）。
 *
 * 事件模型对应后端 `event/models.py`（Pydantic `model_dump(mode="json")` 形态，
 * 字段为 snake_case）。WS 载荷不在 REST OpenAPI 契约（`openapi.json` 仅含
 * REST schema）内，故此处按后端事件模型定义可辨识联合（discriminated
 * union），以 `type` 字段判别；解析入口做运行时校验，畸形载荷返回 null。
 *
 * `{type: "ping"}` 为两条 WS 通道共用的保活消息（空闲 30s 由后端发出），
 * 仅用于判活，不作业务处理（§7.1）。
 */

/** 保活消息（§7.1）。 */
export interface PingMessage {
  type: 'ping'
}

/** 多数事件的载荷：房间号 + 文件路径。 */
export interface FileEventData {
  room_id: number
  path: string
}

/** PostprocessingCompletedEvent 载荷：房间号 + 产物文件列表。 */
export interface PostprocessingCompletedEventData {
  room_id: number
  files: string[]
}

/** Error 事件载荷：异常名 + 详情。 */
export interface ErrorEventData {
  name: string
  detail: string
}

/** `data` 为 `{room_id, path}` 的事件类型名（§7.2）。 */
export const FILE_EVENT_TYPES = [
  'VideoFileCreatedEvent',
  'VideoFileCompletedEvent',
  'DanmakuFileCreatedEvent',
  'DanmakuFileCompletedEvent',
  'RawDanmakuFileCreatedEvent',
  'RawDanmakuFileCompletedEvent',
  'CoverImageDownloadedEvent',
  'VideoPostprocessingCompletedEvent',
] as const

export type FileEventType = (typeof FILE_EVENT_TYPES)[number]

/** 事件公共外壳（BaseEvent：type + id + date + data）。 */
interface EventShell<T extends string, D> {
  type: T
  id: string
  date: string
  data: D
}

export type FileEvent = EventShell<FileEventType, FileEventData>
export type PostprocessingCompletedEvent = EventShell<
  'PostprocessingCompletedEvent',
  PostprocessingCompletedEventData
>
export type ErrorEvent = EventShell<'Error', ErrorEventData>

/** `/ws/v1/events` 全部业务事件的可辨识联合（§7.2）。 */
export type AppEvent = FileEvent | PostprocessingCompletedEvent | ErrorEvent

/** `/ws/v1/exceptions` 消息体：`{type, message, traceback}`（§7.1）。 */
export interface ExceptionMessage {
  type: string
  message: string
  traceback: string
}

/** 判别保活消息。 */
export function isPing(
  msg: AppEvent | ExceptionMessage | PingMessage,
): msg is PingMessage {
  return msg.type === 'ping'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function hasShell(raw: Record<string, unknown>): boolean {
  return (
    typeof raw.type === 'string' &&
    typeof raw.id === 'string' &&
    typeof raw.date === 'string' &&
    isRecord(raw.data)
  )
}

function isFileEventData(data: Record<string, unknown>): boolean {
  return typeof data.room_id === 'number' && typeof data.path === 'string'
}

function isPostprocessingData(data: Record<string, unknown>): boolean {
  return (
    typeof data.room_id === 'number' &&
    Array.isArray(data.files) &&
    data.files.every((f) => typeof f === 'string')
  )
}

function isErrorData(data: Record<string, unknown>): boolean {
  return typeof data.name === 'string' && typeof data.detail === 'string'
}

/**
 * 解析 `/ws/v1/events` 消息：合法业务事件或 ping 返回对应对象，
 * 未知类型/畸形载荷返回 null（调用侧静默丢弃，避免崩溃）。
 */
export function parseEventMessage(raw: unknown): AppEvent | PingMessage | null {
  if (!isRecord(raw) || typeof raw.type !== 'string') return null
  if (raw.type === 'ping') return { type: 'ping' }
  if (!hasShell(raw)) return null
  const data = raw.data as Record<string, unknown>
  const type = raw.type
  if ((FILE_EVENT_TYPES as readonly string[]).includes(type)) {
    return isFileEventData(data) ? (raw as unknown as FileEvent) : null
  }
  if (type === 'PostprocessingCompletedEvent') {
    return isPostprocessingData(data)
      ? (raw as unknown as PostprocessingCompletedEvent)
      : null
  }
  if (type === 'Error') {
    return isErrorData(data) ? (raw as unknown as ErrorEvent) : null
  }
  return null
}

/**
 * 解析 `/ws/v1/exceptions` 消息：`{type, message, traceback}` 或 ping，
 * 畸形载荷返回 null。
 */
export function parseExceptionMessage(
  raw: unknown,
): ExceptionMessage | PingMessage | null {
  if (!isRecord(raw) || typeof raw.type !== 'string') return null
  if (raw.type === 'ping') return { type: 'ping' }
  if (typeof raw.message === 'string' && typeof raw.traceback === 'string') {
    return raw as unknown as ExceptionMessage
  }
  return null
}
