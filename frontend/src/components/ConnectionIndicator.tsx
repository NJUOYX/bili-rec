/**
 * 顶栏实时连接指示灯（frontend-design.md §14.4/§7.3）。
 *
 * 订阅 stores/connection 的聚合三态：绿=已连 / 黄=重连中 / 红=断开，
 * 附文案说明（视觉与含义同 §14.4）。
 */
import { Badge } from 'antd'

import {
  selectIndicator,
  useConnectionStore,
  type ConnectionIndicator as IndicatorState,
} from '../stores/connection'

const INDICATOR_PRESENTATION: Record<
  IndicatorState,
  { status: 'success' | 'warning' | 'error'; text: string }
> = {
  connected: { status: 'success', text: '已连接' },
  reconnecting: { status: 'warning', text: '重连中' },
  disconnected: { status: 'error', text: '已断开' },
}

export function ConnectionIndicator() {
  const indicator = useConnectionStore(selectIndicator)
  const { status, text } = INDICATOR_PRESENTATION[indicator]
  return (
    <span data-testid="connection-indicator" data-state={indicator}>
      <Badge status={status} text={text} />
    </span>
  )
}
