/**
 * 实时推送总线 hook（frontend-design.md §7.3：页面加载即建立两条连接）。
 *
 * 在应用根组件调用一次，同时订阅事件与异常两条 WS 通道；
 * 连接状态经 stores/connection 聚合为顶栏指示灯三态（§14.4）。
 */
import { useEventStream } from './useEventStream'
import { useExceptionStream } from './useExceptionStream'

export function useRealtime(): void {
  useEventStream()
  useExceptionStream()
}
