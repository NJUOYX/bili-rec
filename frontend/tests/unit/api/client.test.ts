/**
 * M28 DT：API 客户端与 ResponseMessage 拆包（frontend-design.md §4/§5）。
 * 覆盖：错误分类、unwrap 各分支、call 网络错误包装、客户端契约集成（MSW）。
 */
import { HttpResponse, http } from 'msw'

import {
  ApiError,
  call,
  classifyCode,
  createApiClient,
  unwrap,
  type FetchResult,
} from '../../../src/api/client'
import { setupMswServer } from '../helpers/msw'

function fetchResult(
  body: unknown,
  init: { status?: number; ok?: boolean } = {},
): FetchResult {
  const status = init.status ?? 200
  const response = new Response(null, { status })
  return status >= 400 ? { error: body, response } : { data: body, response }
}

describe('classifyCode', () => {
  it('404 → not_found', () => {
    expect(classifyCode(404)).toBe('not_found')
  })

  it('403 → forbidden', () => {
    expect(classifyCode(403)).toBe('forbidden')
  })

  it('其余非零码 → business', () => {
    expect(classifyCode(422)).toBe('business')
    expect(classifyCode(500)).toBe('business')
    expect(classifyCode(1)).toBe('business')
  })
})

describe('ApiError', () => {
  it('缺省 kind 时按 code 自动分类', () => {
    expect(new ApiError(404, 'x').kind).toBe('not_found')
    expect(new ApiError(403, 'x').kind).toBe('forbidden')
    expect(new ApiError(500, 'x').kind).toBe('business')
  })

  it('显式 kind 优先，且保留 cause', () => {
    const cause = new TypeError('fetch failed')
    const err = new ApiError(-1, 'boom', 'network', { cause })
    expect(err.kind).toBe('network')
    expect(err.cause).toBe(cause)
    expect(err.name).toBe('ApiError')
  })
})

describe('unwrap', () => {
  it('code=0 且携带 data → 返回 data', () => {
    const data = { total: 1, tasks: [] }
    expect(unwrap(fetchResult({ code: 0, message: '', data }))).toEqual(data)
  })

  it('code=0 无 data（仅提示语）→ 返回 undefined', () => {
    expect(
      unwrap(fetchResult({ code: 0, message: 'Restarting...' })),
    ).toBeUndefined()
  })

  it('code!=0 → 抛业务 ApiError 并携带 message', () => {
    expect(() =>
      unwrap(fetchResult({ code: 409, message: 'Task already exists' })),
    ).toThrowError(
      expect.objectContaining({ code: 409, kind: 'business' }) as Error,
    )
  })

  it('HTTP 404 的统一体（异常处理器）→ not_found', () => {
    expect(() =>
      unwrap(fetchResult({ code: 404, message: 'Not Found' }, { status: 404 })),
    ).toThrowError(expect.objectContaining({ kind: 'not_found' }) as Error)
  })

  it('非统一体的 HTTP 错误（如 422 校验错误）→ 按状态码抛错', () => {
    expect(() =>
      unwrap(fetchResult({ detail: [] }, { status: 422 })),
    ).toThrowError(expect.objectContaining({ code: 422 }) as Error)
  })

  it('2xx 但载荷不符合统一体 → 契约异常', () => {
    expect(() => unwrap(fetchResult({ hello: 'world' }))).toThrowError(
      expect.objectContaining({ code: -1 }) as Error,
    )
  })
})

describe('call', () => {
  it('请求成功 → 透传拆包结果', async () => {
    const data = { pid: 1 }
    await expect(
      call(async () => fetchResult({ code: 0, message: '', data })),
    ).resolves.toEqual(data)
  })

  it('fetch 层异常 → 包装为 network ApiError 并保留 cause', async () => {
    const cause = new TypeError('fetch failed')
    const promise = call(async () => {
      throw cause
    })
    await expect(promise).rejects.toBeInstanceOf(ApiError)
    await expect(promise).rejects.toMatchObject({
      kind: 'network',
      cause,
    })
  })
})

describe('createApiClient（MSW 契约集成）', () => {
  const server = setupMswServer()

  it('默认 baseUrl 取自 window.location.origin，请求命中 /api/v1 路径', async () => {
    server.use(
      http.get('/api/v1/app/info', () =>
        HttpResponse.json({
          code: 0,
          message: '',
          data: { name: 'birec', version: '0.1.0' },
        }),
      ),
    )
    const client = createApiClient()
    const data = await call(() => client.GET('/api/v1/app/info'))
    expect(data).toEqual({ name: 'birec', version: '0.1.0' })
  })

  it('网络失败（HttpResponse.error）→ network ApiError', async () => {
    server.use(http.get('/api/v1/app/info', () => HttpResponse.error()))
    const client = createApiClient()
    await expect(
      call(() => client.GET('/api/v1/app/info')),
    ).rejects.toMatchObject({ kind: 'network' })
  })
})
