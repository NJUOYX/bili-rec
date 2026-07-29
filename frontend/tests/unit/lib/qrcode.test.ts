/**
 * M32 DT：扫码登录状态映射纯函数（§8）。
 */
import { describe, expect, it } from 'vitest'

import {
  QRCODE_HINTS,
  mapPollCode,
  toQrStatus,
  type QrcodeState,
} from '../../../src/lib/qrcode'

describe('mapPollCode', () => {
  it.each([
    [0, 'success'],
    [86101, 'waiting'],
    [86090, 'scanned'],
    [86038, 'expired'],
    [-1, 'error'],
    [99999, 'error'],
  ] as const)('code %i → %s', (code, expected) => {
    expect(mapPollCode(code)).toBe(expected)
  })
})

describe('toQrStatus', () => {
  it.each([
    ['idle', 'loading'],
    ['waiting', 'active'],
    ['success', 'active'],
    ['scanned', 'scanned'],
    ['expired', 'expired'],
    ['error', 'expired'],
  ] as const)('%s → %s', (state, expected) => {
    expect(toQrStatus(state as QrcodeState)).toBe(expected)
  })
})

describe('QRCODE_HINTS', () => {
  it('覆盖全部状态且非空', () => {
    const states: QrcodeState[] = [
      'idle',
      'waiting',
      'scanned',
      'success',
      'expired',
      'error',
    ]
    for (const s of states) {
      expect(QRCODE_HINTS[s]).toBeTruthy()
    }
  })
})
