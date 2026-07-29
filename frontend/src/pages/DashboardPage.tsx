/**
 * 概览 Dashboard（frontend-design.md §14.5）。
 *
 * - 统计卡片行：录制中 / 监控中 / 总任务 / 磁盘进度环 / 总下载速率 sparkline；
 * - 最近事件时间线（复用 EventLogPanel）；
 * - 「录制中」快捷卡片（点击进入详情）。
 * 后端 app/status 暂未暴露磁盘信息，磁盘环缺数据时降级为「—」。
 */
import {
  Card,
  Col,
  Empty,
  Progress,
  Row,
  Space,
  Statistic,
  Typography,
} from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'

import { useAppStatus } from '../api/endpoints/app'
import { useTasksData } from '../api/endpoints/tasks'
import { EventLogPanel } from '../components/EventLogPanel'
import { RateSparkline } from '../components/RateSparkline'
import { StatCard } from '../components/StatCard'
import {
  parseDiskUsage,
  recordingTasks,
  summarizeTasks,
} from '../lib/dashboard'
import { formatRate, toPercent } from '../lib/format'
import { parseTasksPage } from '../lib/task'

/** sparkline 采样上限。 */
const RATE_HISTORY = 30

export function DashboardPage() {
  const navigate = useNavigate()
  const tasksQuery = useTasksData({})
  const appStatus = useAppStatus()

  const page = useMemo(() => parseTasksPage(tasksQuery.data), [tasksQuery.data])
  const summary = useMemo(() => summarizeTasks(page.tasks), [page.tasks])
  const recording = useMemo(() => recordingTasks(page.tasks), [page.tasks])
  const disk = useMemo(() => parseDiskUsage(appStatus.data), [appStatus.data])

  // 总下载速率滚动采样，供 sparkline。
  const [rateHistory, setRateHistory] = useState<number[]>([])
  const lastRate = useRef(0)
  lastRate.current = summary.totalDlRate
  useEffect(() => {
    setRateHistory((prev) => [...prev, lastRate.current].slice(-RATE_HISTORY))
  }, [summary.totalDlRate])

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={8} lg={5}>
          <StatCard title="录制中" value={summary.recording} />
        </Col>
        <Col xs={12} sm={8} lg={5}>
          <StatCard title="监控中" value={summary.monitoring} />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <StatCard title="总任务" value={summary.total} />
        </Col>
        <Col xs={12} sm={12} lg={5}>
          <Card>
            <Statistic
              title="磁盘占用"
              valueRender={() =>
                disk === null ? (
                  <Typography.Text type="secondary">—</Typography.Text>
                ) : (
                  <Progress
                    type="dashboard"
                    size={80}
                    percent={toPercent(disk)}
                  />
                )
              }
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={5}>
          <StatCard
            title="总下载速率"
            value={formatRate(summary.totalDlRate)}
            extra={
              <RateSparkline values={rateHistory} label="总下载速率走势" />
            }
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="录制中" size="small">
            {recording.length === 0 ? (
              <Empty description="当前无录制任务" />
            ) : (
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                {recording.map((task) => (
                  <Card
                    key={task.room_id}
                    size="small"
                    hoverable
                    data-testid="recording-quick-card"
                    onClick={() => navigate(`/tasks/${task.room_id}`)}
                  >
                    <Space
                      style={{
                        justifyContent: 'space-between',
                        width: '100%',
                      }}
                    >
                      <span>
                        {task.room_title || `房间 ${task.room_id}`} ·{' '}
                        {task.user_name}
                      </span>
                      <span>{formatRate(task.task_status.dl_rate)}</span>
                    </Space>
                  </Card>
                ))}
              </Space>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="最近事件" size="small">
            <EventLogPanel limit={8} />
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
