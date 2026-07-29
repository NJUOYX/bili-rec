/**
 * 事件/异常日志面板（frontend-design.md §8.2/§9/§14.5）。
 *
 * 消费 stores/eventLog 的有界缓冲：业务事件时间线（Dashboard 紧凑态复用）
 * 与异常列表。纯订阅展示，不主动拉取。
 */
import { Empty, List, Tag, Typography } from 'antd'

import { useEventLogStore } from '../stores/eventLog'
import type { AppEvent } from '../ws/events'

/** 事件类型 → 中文标签（§7.2 全部业务事件）。 */
export const EVENT_TYPE_LABELS: Record<AppEvent['type'], string> = {
  VideoFileCreatedEvent: '视频文件创建',
  VideoFileCompletedEvent: '视频文件完成',
  DanmakuFileCreatedEvent: '弹幕文件创建',
  DanmakuFileCompletedEvent: '弹幕文件完成',
  RawDanmakuFileCreatedEvent: '原始弹幕创建',
  RawDanmakuFileCompletedEvent: '原始弹幕完成',
  CoverImageDownloadedEvent: '封面已下载',
  VideoPostprocessingCompletedEvent: '视频后处理完成',
  PostprocessingCompletedEvent: '后处理完成',
  Error: '错误',
}

/** 事件的展示描述（文件路径/产物数量/错误详情）。 */
export function describeEvent(event: AppEvent): string {
  if (event.type === 'Error') {
    return `${event.data.name}: ${event.data.detail}`
  }
  if (event.type === 'PostprocessingCompletedEvent') {
    return `房间 ${event.data.room_id} · ${event.data.files.length} 个产物`
  }
  return `房间 ${event.data.room_id} · ${event.data.path}`
}

export interface EventLogPanelProps {
  /** 展示条数上限（紧凑态用）。 */
  limit?: number
}

export function EventLogPanel({ limit }: EventLogPanelProps) {
  const events = useEventLogStore((s) => s.events)
  const shown = limit !== undefined ? events.slice(0, limit) : events

  if (shown.length === 0) {
    return (
      <Empty
        data-testid="event-log-empty"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="暂无事件"
      />
    )
  }
  return (
    <List
      data-testid="event-log-panel"
      size="small"
      dataSource={shown}
      rowKey={(e) => e.id}
      renderItem={(event) => (
        <List.Item>
          <Tag color={event.type === 'Error' ? 'red' : 'blue'}>
            {EVENT_TYPE_LABELS[event.type]}
          </Tag>
          <Typography.Text
            type="secondary"
            style={{ flex: 1 }}
            ellipsis={{ tooltip: describeEvent(event) }}
          >
            {describeEvent(event)}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {new Date(event.date).toLocaleTimeString('zh-CN', {
              hour12: false,
            })}
          </Typography.Text>
        </List.Item>
      )}
    />
  )
}
