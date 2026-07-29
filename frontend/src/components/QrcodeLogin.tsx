/**
 * TV 扫码登录组件（frontend-design.md §8 登录页 / §8.2 QrcodeLogin）。
 *
 * 流程：请求二维码 → 每 2s 轮询状态 → 按业务码驱动状态机
 * （waiting/scanned/success/expired/error）→ 成功后失效设置缓存。
 * AntD 内置 QRCode 组件渲染，避免额外二维码依赖。
 */
import { App as AntdApp, Button, Flex, QRCode, Typography } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { pollQrcode, requestQrcode } from '../api/endpoints/auth'
import { queryKeys } from '../api/queryKeys'
import { toMessage } from '../lib/errors'
import {
  QRCODE_HINTS,
  mapPollCode,
  toQrStatus,
  type QrcodeState,
} from '../lib/qrcode'

const POLL_INTERVAL_MS = 2000

export function QrcodeLogin() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const [url, setUrl] = useState('')
  const [state, setState] = useState<QrcodeState>('idle')
  const authCodeRef = useRef('')

  const refresh = useCallback(async () => {
    setState('idle')
    setUrl('')
    try {
      const qr = await requestQrcode()
      authCodeRef.current = qr.auth_code
      setUrl(qr.url)
      setState('waiting')
    } catch (e) {
      setState('error')
      message.error(toMessage(e))
    }
  }, [message])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // 轮询：仅在 waiting/scanned 时进行。
  useEffect(() => {
    if (state !== 'waiting' && state !== 'scanned') return
    let cancelled = false
    const timer = setInterval(async () => {
      try {
        const res = await pollQrcode(authCodeRef.current)
        if (cancelled) return
        const next = mapPollCode(res.code)
        setState(next)
        if (next === 'success') {
          message.success('登录成功')
          await queryClient.invalidateQueries({
            queryKey: queryKeys.settings(),
          })
        }
      } catch (e) {
        if (cancelled) return
        setState('error')
        message.error(toMessage(e))
      }
    }, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [state, message, queryClient])

  const showRefresh = state === 'expired' || state === 'error'

  return (
    <Flex vertical align="center" gap={16} data-testid="qrcode-login">
      <QRCode
        value={url || '-'}
        status={toQrStatus(state)}
        size={200}
        onRefresh={() => void refresh()}
      />
      <Typography.Text type={state === 'success' ? 'success' : 'secondary'}>
        {QRCODE_HINTS[state]}
      </Typography.Text>
      {showRefresh && (
        <Button type="primary" onClick={() => void refresh()}>
          刷新二维码
        </Button>
      )}
    </Flex>
  )
}
