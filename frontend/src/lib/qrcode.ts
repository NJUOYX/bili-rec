/**
 * 扫码登录轮询状态映射（frontend-design.md §8 登录页）。
 *
 * B 站 TV 扫码登录 poll 接口以业务码表达「进行中状态」，非错误：
 * 0=成功，86101=未扫码，86090=已扫码待确认，86038=二维码失效，其余=错误。
 */
export type QrcodeState =
  'idle' | 'waiting' | 'scanned' | 'success' | 'expired' | 'error'

export function mapPollCode(code: number): QrcodeState {
  switch (code) {
    case 0:
      return 'success'
    case 86101:
      return 'waiting'
    case 86090:
      return 'scanned'
    case 86038:
      return 'expired'
    default:
      return 'error'
  }
}

/** QrcodeState → AntD QRCode 组件 status（active/scanned/expired/loading）。 */
export function toQrStatus(
  state: QrcodeState,
): 'active' | 'scanned' | 'expired' | 'loading' {
  switch (state) {
    case 'scanned':
      return 'scanned'
    case 'expired':
    case 'error':
      return 'expired'
    case 'idle':
      return 'loading'
    default:
      return 'active'
  }
}

/** 状态说明文案。 */
export const QRCODE_HINTS: Record<QrcodeState, string> = {
  idle: '正在获取二维码…',
  waiting: '请使用哔哩哔哩手机客户端扫码',
  scanned: '已扫码，请在手机上确认登录',
  success: '登录成功',
  expired: '二维码已失效，请刷新',
  error: '登录失败，请重试',
}
