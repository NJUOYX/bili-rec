/**
 * 类型安全 API 客户端 + ResponseMessage 拆包（frontend-design.md §4/§5）。
 *
 * - 路径/方法/参数/响应类型全部由 `schema.d.ts`（openapi-typescript 生成）派生，
 *   禁止手写接口类型。
 * - 后端统一响应体 `ResponseMessage{code, message, data?}`：`code !== 0` 视为
 *   业务错误抛出 `ApiError`，成功返回 `data`（可能缺省）。
 * - 错误按 §4 分类：未找到（404）/ 禁止（403）/ 业务错误 / 网络错误。
 */
import createClient from 'openapi-fetch'

import type { paths } from './schema'

/** 后端统一响应体（web/models.py ResponseMessage 的运行时形态）。 */
export interface ResponseMessage {
  code: number
  message: string
  data?: Record<string, unknown>
}

/** 错误分类（frontend-design.md §4）。 */
export type ApiErrorKind = 'not_found' | 'forbidden' | 'business' | 'network'

/** 按业务码/HTTP 状态码分类错误。 */
export function classifyCode(code: number): ApiErrorKind {
  if (code === 404) return 'not_found'
  if (code === 403) return 'forbidden'
  return 'business'
}

/** 统一 API 错误：携带业务码与分类，交由 TanStack Query / 全局通知处理。 */
export class ApiError extends Error {
  readonly code: number
  readonly kind: ApiErrorKind

  constructor(
    code: number,
    message: string,
    kind?: ApiErrorKind,
    options?: ErrorOptions,
  ) {
    super(message, options)
    this.name = 'ApiError'
    this.code = code
    this.kind = kind ?? classifyCode(code)
  }
}

function isResponseMessage(value: unknown): value is ResponseMessage {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { code?: unknown }).code === 'number' &&
    typeof (value as { message?: unknown }).message === 'string'
  )
}

/** openapi-fetch 单次请求结果的结构化视图（data/error 互斥）。 */
export interface FetchResult {
  data?: unknown
  error?: unknown
  response: Response
}

/**
 * 拆包统一响应体：
 * - 载荷为 ResponseMessage 且 `code === 0` → 返回 `data`（可能为 undefined）；
 * - `code !== 0` → 抛 `ApiError`（404/403/业务分类）；
 * - 非统一体（如 FastAPI 422 校验错误）→ 按 HTTP 状态抛 `ApiError`；
 * - 2xx 但载荷不符合统一体 → 视为契约异常抛 `ApiError`。
 */
export function unwrap(
  result: FetchResult,
): Record<string, unknown> | undefined {
  const body = result.data ?? result.error
  if (isResponseMessage(body)) {
    if (body.code !== 0) {
      throw new ApiError(body.code, body.message)
    }
    return body.data
  }
  if (!result.response.ok) {
    throw new ApiError(
      result.response.status,
      `HTTP ${result.response.status} ${result.response.statusText}`.trim(),
    )
  }
  throw new ApiError(-1, 'Malformed response body (expected ResponseMessage)')
}

/**
 * 执行请求并拆包；fetch 层异常（断网/DNS/代理失败）归类为 `network`。
 * 领域 hooks 的 queryFn/mutationFn 统一经此入口，保证错误形态一致。
 */
export async function call(
  request: () => Promise<FetchResult>,
): Promise<Record<string, unknown> | undefined> {
  let result: FetchResult
  try {
    result = await request()
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : 'Network error'
    throw new ApiError(-1, message, 'network', { cause })
  }
  return unwrap(result)
}

/**
 * 默认基地址：浏览器内取当前源（开发期由 Vite 代理把 `/api` 转发到后端，
 * 生产由后端直接托管，均为同源），非浏览器环境回退为空串。
 */
function defaultBaseUrl(): string {
  return typeof window === 'undefined' ? '' : window.location.origin
}

/**
 * 创建类型安全客户端；`baseUrl` 可注入以便测试或反向代理场景。
 * fetch 惰性绑定到 globalThis：避免模块加载期捕获旧引用，
 * 使运行期补丁（MSW 拦截器等）对单例客户端同样生效。
 */
export function createApiClient(baseUrl: string = defaultBaseUrl()) {
  return createClient<paths>({
    baseUrl,
    fetch: (request) => globalThis.fetch(request),
  })
}

/** 应用级单例客户端。 */
export const api = createApiClient()
