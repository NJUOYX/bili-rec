/**
 * 任务列表页（frontend-design.md §14.6）。
 *
 * 卡片网格为主（响应式 xxl:4 / xl:3 / md:2 / xs:1），顶部工具条：
 * - 筛选器（TASK_FILTER_OPTIONS → GET /tasks/data 的 select）；
 * - 批量操作（全部启动/停止、录制器开关、刷新信息）；
 * - 空态/加载态。
 * 运行态速率无 WS 推送，列表默认 2s 短轮询（useTasksData）。
 */
import { ReloadOutlined } from '@ant-design/icons'
import {
  App as AntdApp,
  Button,
  Col,
  Empty,
  Row,
  Segmented,
  Space,
  Spin,
} from 'antd'
import { useMemo, useState } from 'react'

import {
  useBatchRefreshInfo,
  useBatchSetRecorder,
  useBatchStart,
  useBatchStop,
  useDeleteTask,
  useRefreshTaskInfo,
  useSetTaskRecorder,
  useStartTask,
  useStopTask,
  useTasksData,
} from '../../api/endpoints/tasks'
import { TaskCard } from '../../components/TaskCard'
import {
  filterToSelect,
  parseTasksPage,
  TASK_FILTER_OPTIONS,
  type TaskFilter,
} from '../../lib/task'

/** 卡片网格响应式列宽（AntD 24 栅格）。 */
const GRID_SPAN = { xs: 24, sm: 12, md: 12, lg: 8, xl: 8, xxl: 6 }

export function TaskListPage() {
  const { message } = AntdApp.useApp()
  const [filter, setFilter] = useState<TaskFilter>('all')
  const query = useMemo(() => ({ select: filterToSelect(filter) }), [filter])
  const { data, isLoading, isError, refetch } = useTasksData(query)
  const page = useMemo(() => parseTasksPage(data), [data])

  const startTask = useStartTask()
  const stopTask = useStopTask()
  const setRecorder = useSetTaskRecorder()
  const refreshTask = useRefreshTaskInfo()
  const deleteTask = useDeleteTask()
  const batchStart = useBatchStart()
  const batchStop = useBatchStop()
  const batchRecorder = useBatchSetRecorder()
  const batchRefresh = useBatchRefreshInfo()

  const busy =
    startTask.isPending ||
    stopTask.isPending ||
    setRecorder.isPending ||
    refreshTask.isPending ||
    deleteTask.isPending
  const batchBusy =
    batchStart.isPending ||
    batchStop.isPending ||
    batchRecorder.isPending ||
    batchRefresh.isPending

  const ok = (label: string) => () => message.success(`${label}成功`)

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
        <Segmented
          value={filter}
          onChange={(value) => setFilter(value as TaskFilter)}
          options={TASK_FILTER_OPTIONS.map((o) => ({
            value: o.value,
            label: o.label,
          }))}
        />
        <Space wrap>
          <Button
            disabled={batchBusy}
            onClick={() => batchStart.mutate([], { onSuccess: ok('全部启动') })}
          >
            全部启动
          </Button>
          <Button
            disabled={batchBusy}
            onClick={() => batchStop.mutate([], { onSuccess: ok('全部停止') })}
          >
            全部停止
          </Button>
          <Button
            disabled={batchBusy}
            onClick={() =>
              batchRecorder.mutate(
                { enabled: true },
                { onSuccess: ok('全部开启录制器') },
              )
            }
          >
            全部录制
          </Button>
          <Button
            icon={<ReloadOutlined />}
            disabled={batchBusy}
            onClick={() =>
              batchRefresh.mutate(undefined, { onSuccess: ok('刷新信息') })
            }
          >
            刷新信息
          </Button>
        </Space>
      </Space>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin />
        </div>
      ) : isError ? (
        <Empty description="加载失败">
          <Button onClick={() => refetch()}>重试</Button>
        </Empty>
      ) : page.tasks.length === 0 ? (
        <Empty description="暂无任务" />
      ) : (
        <Row gutter={[16, 16]} data-testid="task-grid">
          {page.tasks.map((task) => (
            <Col key={task.room_id} {...GRID_SPAN}>
              <TaskCard
                task={task}
                busy={busy}
                onStart={(id) =>
                  startTask.mutate(id, { onSuccess: ok('启动') })
                }
                onStop={(id) => stopTask.mutate(id, { onSuccess: ok('停止') })}
                onToggleRecorder={(id, enabled) =>
                  setRecorder.mutate(
                    { roomId: id, enabled },
                    { onSuccess: ok(enabled ? '开启录制器' : '关闭录制器') },
                  )
                }
                onRefresh={(id) =>
                  refreshTask.mutate(id, { onSuccess: ok('刷新') })
                }
                onDelete={(id) =>
                  deleteTask.mutate(id, { onSuccess: ok('删除') })
                }
              />
            </Col>
          ))}
        </Row>
      )}
    </Space>
  )
}
