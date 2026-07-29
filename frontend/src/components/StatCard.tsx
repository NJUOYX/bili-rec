/**
 * 概览统计卡片（frontend-design.md §14.5：Dashboard 统计卡片行）。
 */
import { Card, Statistic } from 'antd'
import type { ReactNode } from 'react'

export interface StatCardProps {
  title: string
  /** 主数值（数字或已格式化文本）。 */
  value: number | string
  suffix?: ReactNode
  prefix?: ReactNode
  loading?: boolean
  /** 底部扩展区（进度环/sparkline 等）。 */
  extra?: ReactNode
}

export function StatCard({
  title,
  value,
  suffix,
  prefix,
  loading,
  extra,
}: StatCardProps) {
  return (
    <Card size="small" data-testid="stat-card">
      <Statistic
        title={title}
        value={value}
        suffix={suffix}
        prefix={prefix}
        loading={loading}
      />
      {extra}
    </Card>
  )
}
