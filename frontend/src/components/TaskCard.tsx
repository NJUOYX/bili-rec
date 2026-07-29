/**
 * 任务卡片（frontend-design.md §14.6）。
 *
 * 展示以 `/tasks/data` 的 TaskData 为准（缺失字段降级）：
 * - 封面区 16:9，无封面字段 → 分区名占位；左上直播状态角标；
 * - 主播/房间标题/分区信息 + StatusBadge；
 * - 录制中：RateGauge（下载/录制速率）+ ProgressBar（后处理进度）；
 * - 操作区：启停监控、录制器开关、更多（刷新信息/删除/详情）；
 * - 录制中卡片主色呼吸描边（CSS 动画 .task-card--recording）。
 *
 * 手动切割（cut）已在后端功能范围决策中移除，不设切割按钮。
 */
import {
  DeleteOutlined,
  EllipsisOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  StopOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import {
  App as AntdApp,
  Button,
  Card,
  Dropdown,
  Space,
  Switch,
  Tag,
  theme,
} from 'antd'
import { useNavigate } from 'react-router'

import type { TaskDataView } from '../lib/task'
import { ProgressBar } from './ProgressBar'
import { RateGauge } from './RateGauge'
import { StatusBadge } from './StatusBadge'

export interface TaskCardActions {
  onStart: (roomId: number) => void
  onStop: (roomId: number) => void
  onToggleRecorder: (roomId: number, enabled: boolean) => void
  onRefresh: (roomId: number) => void
  onDelete: (roomId: number) => void
  /** 任一操作进行中 → 禁用按钮，避免重复提交。 */
  busy?: boolean
}

export interface TaskCardProps extends TaskCardActions {
  task: TaskDataView
}

export function TaskCard({
  task,
  onStart,
  onStop,
  onToggleRecorder,
  onRefresh,
  onDelete,
  busy = false,
}: TaskCardProps) {
  const navigate = useNavigate()
  const { modal } = AntdApp.useApp()
  const { token } = theme.useToken()
  const status = task.task_status
  const recording = status.running_status === 'recording'
  const monitorOn = status.monitor_enabled

  const confirmDelete = () => {
    modal.confirm({
      title: `删除任务 ${task.room_id}？`,
      content: `将移除房间「${task.room_title || task.user_name}」的录制任务。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => onDelete(task.room_id),
    })
  }

  return (
    <Card
      hoverable
      data-testid="task-card"
      data-recording={recording}
      className={recording ? 'task-card task-card--recording' : 'task-card'}
      styles={{ body: { padding: 16 } }}
      cover={
        <div
          style={{
            position: 'relative',
            aspectRatio: '16 / 9',
            background: token.colorFillSecondary,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: token.colorTextSecondary,
            fontSize: 14,
            overflow: 'hidden',
          }}
        >
          <span>{task.parent_area || task.area || '未知分区'}</span>
          <Tag
            color={task.live_status ? 'red' : 'default'}
            style={{ position: 'absolute', top: 8, left: 8, margin: 0 }}
          >
            {task.live_status ? '直播中' : '未开播'}
          </Tag>
        </div>
      }
    >
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Button
          type="link"
          style={{
            padding: 0,
            height: 'auto',
            textAlign: 'left',
            fontWeight: 600,
          }}
          onClick={() => navigate(`/tasks/${task.room_id}`)}
        >
          {task.room_title || `房间 ${task.room_id}`}
        </Button>
        <div style={{ color: token.colorTextSecondary, fontSize: 13 }}>
          {task.user_name || '未知主播'} · 房间 {task.room_id}
          {task.area ? ` · ${task.area}` : ''}
        </div>
        <StatusBadge status={status} />
        {recording && (
          <>
            <RateGauge dlRate={status.dl_rate} recRate={status.rec_rate} />
            {status.postprocessing_progress > 0 && (
              <ProgressBar
                ratio={status.postprocessing_progress}
                label="后处理"
              />
            )}
          </>
        )}
        <Space size={8} align="center" wrap>
          {monitorOn ? (
            <Button
              size="small"
              icon={<StopOutlined />}
              disabled={busy}
              onClick={() => onStop(task.room_id)}
            >
              停止
            </Button>
          ) : (
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              disabled={busy}
              onClick={() => onStart(task.room_id)}
            >
              启动
            </Button>
          )}
          <Space size={4} align="center">
            <VideoCameraOutlined style={{ color: token.colorTextSecondary }} />
            <Switch
              size="small"
              checked={status.recorder_enabled}
              disabled={busy}
              onChange={(checked) => onToggleRecorder(task.room_id, checked)}
              aria-label="录制器开关"
            />
          </Space>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'refresh',
                  icon: <ReloadOutlined />,
                  label: '刷新信息',
                },
                { key: 'detail', label: '查看详情' },
                {
                  key: 'delete',
                  icon: <DeleteOutlined />,
                  label: '删除任务',
                  danger: true,
                },
              ],
              onClick: ({ key }) => {
                if (key === 'refresh') onRefresh(task.room_id)
                else if (key === 'detail') navigate(`/tasks/${task.room_id}`)
                else if (key === 'delete') confirmDelete()
              },
            }}
          >
            <Button
              size="small"
              icon={<EllipsisOutlined />}
              aria-label="更多操作"
            />
          </Dropdown>
        </Space>
      </Space>
    </Card>
  )
}
