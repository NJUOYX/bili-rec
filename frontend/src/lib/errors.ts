/**
 * API 错误的展示层格式化（frontend-design.md §4/§9）。
 */
import { ApiError } from '../api/client'

/** 错误分类 → 通知标题（§4 分类）。 */
const ERROR_TITLES: Record<string, string> = {
  not_found: '资源不存在',
  forbidden: '操作被禁止',
  business: '业务错误',
  network: '网络错误',
}

/** 把任意错误格式化为通知文案（标题 + 描述）。 */
export function describeApiError(error: unknown): {
  message: string
  description: string
} {
  if (error instanceof ApiError) {
    return {
      message: ERROR_TITLES[error.kind] ?? '业务错误',
      description: error.message,
    }
  }
  return {
    message: '未知错误',
    description: error instanceof Error ? error.message : String(error),
  }
}

/** 单行错误文案（标题：描述），用于 message.error / Alert。 */
export function toMessage(error: unknown): string {
  const { message, description } = describeApiError(error)
  return description ? `${message}：${description}` : message
}
