/**
 * 通用占位页（供尚未实现的路由使用，随对应里程碑替换为真实实现）。
 */
import { Empty, Typography } from 'antd'

export interface PlaceholderPageProps {
  title: string
  hint?: string
}

export function PlaceholderPage({ title, hint }: PlaceholderPageProps) {
  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3}>{title}</Typography.Title>
      <Empty description={hint ?? '功能开发中'} />
    </div>
  )
}
