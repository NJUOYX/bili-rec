/**
 * 任务详情页（frontend-design.md §8/§14.6）。
 *
 * 信息头（主播/房间/直播状态/运行状态 + 单任务操作）+ 标签页：
 * 状态/参数/元数据/Profile/视频/弹幕。子资源响应为无类型 object，
 * 除「状态」用 parseTaskData 结构化展示外，其余以 JSON 视图降级呈现。
 */
import {
  PlayCircleOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons'
import {
  App as AntdApp,
  Button,
  Card,
  Descriptions,
  Space,
  Spin,
  Switch,
  Tabs,
  Typography,
} from 'antd'
import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router'

import {
  useRefreshTaskInfo,
  useSetTaskRecorder,
  useStartTask,
  useStopTask,
  useTaskData,
  useTaskDanmakus,
  useTaskMetadata,
  useTaskParam,
  useTaskProfile,
  useTaskVideos,
} from '../../api/endpoints/tasks'
import { StatusBadge } from '../../components/StatusBadge'
import { formatBytes, formatDuration, formatRate } from '../../lib/format'
import { parseTaskData, RUNNING_STATUS_LABELS } from '../../lib/task'

function JsonView({ data }: { data: unknown }) {
  return (
    <pre
      data-testid="json-view"
      style={{
        maxHeight: 480,
        overflow: 'auto',
        fontSize: 12,
        margin: 0,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
      }}
    >
      {JSON.stringify(data ?? null, null, 2)}
    </pre>
  )
}

export function TaskDetailPage() {
  const { roomId: roomIdParam } = useParams<{ roomId: string }>()
  const roomId = Number(roomIdParam)
  const navigate = useNavigate()
  const { message } = AntdApp.useApp()

  const dataQuery = useTaskData(roomId)
  const paramQuery = useTaskParam(roomId)
  const metadataQuery = useTaskMetadata(roomId)
  const profileQuery = useTaskProfile(roomId)
  const videosQuery = useTaskVideos(roomId)
  const danmakusQuery = useTaskDanmakus(roomId)

  const startTask = useStartTask()
  const stopTask = useStopTask()
  const setRecorder = useSetTaskRecorder()
  const refreshTask = useRefreshTaskInfo()
  const busy =
    startTask.isPending ||
    stopTask.isPending ||
    setRecorder.isPending ||
    refreshTask.isPending

  const task = useMemo(() => parseTaskData(dataQuery.data), [dataQuery.data])
  const ok = (label: string) => () => message.success(`${label}成功`)

  if (Number.isNaN(roomId)) {
    return <Typography.Text type="danger">无效的房间号</Typography.Text>
  }
  if (dataQuery.isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin />
      </div>
    )
  }
  if (!task) {
    return (
      <Card>
        <Typography.Text type="danger">任务不存在或加载失败</Typography.Text>
        <div style={{ marginTop: 16 }}>
          <Button onClick={() => navigate('/tasks')}>返回列表</Button>
        </div>
      </Card>
    )
  }

  const status = task.task_status

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space
            style={{ justifyContent: 'space-between', width: '100%' }}
            align="start"
            wrap
          >
            <div>
              <Typography.Title level={4} style={{ margin: 0 }}>
                {task.room_title || `房间 ${task.room_id}`}
              </Typography.Title>
              <Typography.Text type="secondary">
                {task.user_name || '未知主播'} · 房间 {task.room_id} ·{' '}
                {task.area || '未知分区'}
              </Typography.Text>
            </div>
            <Space wrap>
              {status.monitor_enabled ? (
                <Button
                  icon={<StopOutlined />}
                  disabled={busy}
                  onClick={() =>
                    stopTask.mutate(roomId, { onSuccess: ok('停止') })
                  }
                >
                  停止
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  disabled={busy}
                  onClick={() =>
                    startTask.mutate(roomId, { onSuccess: ok('启动') })
                  }
                >
                  启动
                </Button>
              )}
              <Space size={4} align="center">
                录制器
                <Switch
                  checked={status.recorder_enabled}
                  disabled={busy}
                  onChange={(enabled) =>
                    setRecorder.mutate(
                      { roomId, enabled },
                      { onSuccess: ok(enabled ? '开启录制器' : '关闭录制器') },
                    )
                  }
                />
              </Space>
              <Button
                icon={<ReloadOutlined />}
                disabled={busy}
                onClick={() =>
                  refreshTask.mutate(roomId, { onSuccess: ok('刷新') })
                }
              >
                刷新信息
              </Button>
            </Space>
          </Space>
          <StatusBadge status={status} />
        </Space>
      </Card>

      <Card>
        <Tabs
          defaultActiveKey="status"
          items={[
            {
              key: 'status',
              label: '状态',
              children: (
                <Descriptions column={{ xs: 1, sm: 2 }} size="small" bordered>
                  <Descriptions.Item label="运行状态">
                    {RUNNING_STATUS_LABELS[status.running_status]}
                  </Descriptions.Item>
                  <Descriptions.Item label="直播状态">
                    {task.live_status ? '直播中' : '未开播'}
                  </Descriptions.Item>
                  <Descriptions.Item label="下载速率">
                    {formatRate(status.dl_rate)}
                  </Descriptions.Item>
                  <Descriptions.Item label="录制速率">
                    {formatRate(status.rec_rate)}
                  </Descriptions.Item>
                  <Descriptions.Item label="已下载">
                    {formatBytes(status.dl_total)}
                  </Descriptions.Item>
                  <Descriptions.Item label="已录制时长">
                    {formatDuration(status.rec_elapsed)}
                  </Descriptions.Item>
                  <Descriptions.Item label="流格式">
                    {status.real_stream_format || '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label="录制路径">
                    {status.recording_path || '—'}
                  </Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'param',
              label: '参数',
              children: <JsonView data={paramQuery.data} />,
            },
            {
              key: 'metadata',
              label: '元数据',
              children: <JsonView data={metadataQuery.data} />,
            },
            {
              key: 'profile',
              label: 'Profile',
              children: <JsonView data={profileQuery.data} />,
            },
            {
              key: 'videos',
              label: '视频',
              children: <JsonView data={videosQuery.data} />,
            },
            {
              key: 'danmakus',
              label: '弹幕',
              children: <JsonView data={danmakusQuery.data} />,
            },
          ]}
        />
      </Card>
    </Space>
  )
}
