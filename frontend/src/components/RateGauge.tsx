/**
 * 速率仪表（frontend-design.md §8.2/§14.6：录制中显示下载/录制速率）。
 */
import { DownloadOutlined, VideoCameraOutlined } from '@ant-design/icons'
import { Space, Typography } from 'antd'

import { formatRate } from '../lib/format'

export interface RateGaugeProps {
  /** 下载速率（B/s）。 */
  dlRate: number
  /** 录制速率（B/s）。 */
  recRate: number
}

/** 紧凑双速率展示：下载 ↓ / 录制 ●。 */
export function RateGauge({ dlRate, recRate }: RateGaugeProps) {
  return (
    <Space size="middle" data-testid="rate-gauge">
      <Typography.Text type="secondary">
        <DownloadOutlined aria-label="下载速率" /> {formatRate(dlRate)}
      </Typography.Text>
      <Typography.Text type="secondary">
        <VideoCameraOutlined aria-label="录制速率" /> {formatRate(recRate)}
      </Typography.Text>
    </Space>
  )
}
