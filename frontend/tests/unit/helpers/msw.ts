/**
 * MSW 测试服务器辅助：在测试文件内一行接入 Mock 后端。
 * 依据 openapi.json 契约提供响应，禁止手写偏离契约的响应体。
 */
import type { RequestHandler } from 'msw'
import { setupServer, type SetupServer } from 'msw/node'

/** 注册 MSW server 生命周期（beforeAll/afterEach/afterAll），返回 server 供追加 handler。 */
export function setupMswServer(...handlers: RequestHandler[]): SetupServer {
  const server = setupServer(...handlers)
  beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
  afterEach(() => server.resetHandlers())
  afterAll(() => server.close())
  return server
}
