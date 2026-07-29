/**
 * 认证域 hooks：TV 扫码登录（frontend-design.md §6.1 / §8 登录页）。
 *
 * - requestQrcode：GET /qrcode/login → { url, auth_code }。
 * - pollQrcode：POST /qrcode/login/poll，返回完整 ResponseMessage（code 即状态，
 *   不抛错），由调用方按 code 映射登录状态。
 */
import { api, call, callResponse, type ResponseMessage } from '../client'

export interface QrcodeData {
  url: string
  auth_code: string
}

/** 请求一张新的 TV 登录二维码。 */
export async function requestQrcode(): Promise<QrcodeData> {
  const data = await call(() => api.GET('/api/v1/qrcode/login'))
  return (data ?? {}) as unknown as QrcodeData
}

/** 轮询扫码状态（返回原始 ResponseMessage，code 即状态）。 */
export async function pollQrcode(authCode: string): Promise<ResponseMessage> {
  return callResponse(() =>
    api.POST('/api/v1/qrcode/login/poll', {
      body: { auth_code: authCode } as never,
    }),
  )
}
