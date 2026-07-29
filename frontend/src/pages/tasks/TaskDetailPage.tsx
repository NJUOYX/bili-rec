/**
 * 任务详情页（frontend-design.md §8/§14.6）。
 *
 * 信息头（主播/房间/直播状态/运行状态 + 单任务操作）+ 标签页：
 * 状态/参数/元数据用 Descriptions、视频/弹幕文件明细用表格展示；
 * Profile 契约上为自由 ffprobe 字典，无固定字段，仍以 JSON 视图呈现。
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
  Table,
  Tabs,
  Tag,
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
import {
  formatBytes,
  formatDuration,
  formatRate,
  formatTimestamp,
} from '../../lib/format'
import {
  type FileDetailView,
  FILE_STATUS_LABELS,
  parseFileDetails,
  parseTaskData,
  RUNNING_STATUS_LABELS,
  toFieldEntries,
} from '../../lib/task'

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

/** 无类型子资源的键值展示（参数/元数据）。 */
function FieldsView({ data }: { data: unknown }) {
  const entries = toFieldEntries(data)
  if (entries.length === 0) {
    return <Typography.Text type="secondary">暂无数据</Typography.Text>
  }
  return (
    <Descriptions column={{ xs: 1, sm: 2 }} size="small" bordered>
      {entries.map(({ key, label, value }) => (
        <Descriptions.Item key={key} label={label}>
          {renderFieldValue(key, value)}
        </Descriptions.Item>
      ))}
    </Descriptions>
  )
}

function renderFieldValue(key: string, value: unknown) {
  if (typeof value === 'boolean') return value ? '已启用' : '已停用'
  if (key.endsWith('_time') && typeof value === 'number') {
    return formatTimestamp(value)
  }
  if (value === null || value === '') return '—'
  return String(value)
}

/** 视频/弹幕文件明细表（路径 + 体积 + 状态，设计 §5.10）。 */
function FilesView({
  files,
  empty,
}: {
  files: FileDetailView[]
  empty: string
}) {
  return (
    <Table<FileDetailView>
      dataSource={files}
      rowKey="path"
      size="small"
      pagination={false}
      locale={{ emptyText: empty }}
      columns={[
        {
          title: '文件',
          dataIndex: 'path',
          // 路径很长，折叠为文件名并保留完整路径供悬停/复制。
          render: (path: string) => (
            <Typography.Text copyable={{ text: path }} title={path}>
              {path.split('/').pop() || path}
            </Typography.Text>
          ),
        },
        {
          title: '大小',
          dataIndex: 'size',
          width: 120,
          render: (size: number) => formatBytes(size),
        },
        {
          title: '状态',
          dataIndex: 'status',
          width: 120,
          render: (status: string) => (
            <Tag color={status === 'recording' ? 'processing' : undefined}>
              {FILE_STATUS_LABELS[status] ?? status}
            </Tag>
          ),
        },
      ]}
    />
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
  const videos = useMemo(
    () => parseFileDetails(videosQuery.data, 'videos'),
    [videosQuery.data],
  )
  const danmakus = useMemo(
    () => parseFileDetails(danmakusQuery.data, 'danmakus'),
    [danmakusQuery.data],
  )
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
              children: <FieldsView data={paramQuery.data} />,
            },
            {
              key: 'metadata',
              label: '元数据',
              children: <FieldsView data={metadataQuery.data} />,
            },
            {
              key: 'profile',
              label: 'Profile',
              children: <JsonView data={profileQuery.data} />,
            },
            {
              key: 'videos',
              label: '视频',
              children: (
                <FilesView files={videos} empty="未在录制，暂无视频文件" />
              ),
            },
            {
              key: 'danmakus',
              label: '弹幕',
              children: (
                <FilesView files={danmakus} empty="未在录制，暂无弹幕文件" />
              ),
            },
          ]}
        />
      </Card>
    </Space>
  )
}
