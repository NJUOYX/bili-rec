/**
 * 分组级提交状态（frontend-design.md §8.1）。
 *
 * 设置页各分组共用一个 PATCH mutation，直接用 `isPending` 会让所有分组的保存
 * 按钮同时转圈；用集合记录正在提交的分组，连点多组时也能各自独立结束。
 */
import { useState } from 'react'

export interface PendingGroups {
  /** 该分组是否正在提交。 */
  isPending: (groupKey: string) => boolean
  /** 标记分组进入/退出提交中。 */
  setPending: (groupKey: string, pending: boolean) => void
}

export function usePendingGroups(): PendingGroups {
  const [groups, setGroups] = useState<string[]>([])
  return {
    isPending: (groupKey) => groups.includes(groupKey),
    setPending: (groupKey, pending) =>
      setGroups((prev) =>
        pending
          ? [...prev, groupKey]
          : // 同组可能有多次在途提交，只移除一个占位。
            prev.filter((_, i) => i !== prev.indexOf(groupKey)),
      ),
  }
}
