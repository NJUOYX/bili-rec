/**
 * 关于页（frontend-design.md §8）。
 *
 * 汇总应用信息（名称/版本/Python/PID）、运行状态（是否启动/任务数/录制数）、
 * 最新版本比对、目录可用性校验，以及重启/退出等进程操作（Popconfirm 二次确认）。
 */
import {
  App as AntdApp,
  Button,
  Card,
  Descriptions,
  Flex,
  Input,
  Popconfirm,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'

import {
  useAppInfo,
  useAppStatus,
  useExitApp,
  useLatestVersion,
  useRestartApp,
  useValidateDir,
} from '../api/endpoints/app'
import { toMessage } from '../lib/errors'

function str(v: unknown): string {
  return v == null ? '-' : String(v)
}

export function AboutPage() {
  const { message } = AntdApp.useApp()
  const info = useAppInfo()
  const status = useAppStatus()
  const latest = useLatestVersion()
  const validateDir = useValidateDir()
  const restart = useRestartApp()
  const exit = useExitApp()

  const [dir, setDir] = useState('')

  const current = str(latest.data?.current ?? info.data?.version)
  const newest = latest.data?.version as string | undefined
  const hasUpdate = Boolean(newest && current !== '-' && newest !== current)

  async function onValidate() {
    try {
      const data = await validateDir.mutateAsync(dir)
      message.success(`目录可用：${str(data?.path)}`)
    } catch (e) {
      message.error(toMessage(e))
    }
  }

  async function onRestart() {
    try {
      await restart.mutateAsync()
      message.success('已发送重启指令')
    } catch (e) {
      message.error(toMessage(e))
    }
  }

  async function onExit() {
    try {
      await exit.mutateAsync()
      message.success('已发送退出指令')
    } catch (e) {
      message.error(toMessage(e))
    }
  }

  return (
    <Flex vertical gap={16} data-testid="about-page">
      <Card title="应用信息" loading={info.isLoading}>
        <Descriptions column={{ xs: 1, sm: 2 }} size="small">
          <Descriptions.Item label="名称">
            {str(info.data?.name)}
          </Descriptions.Item>
          <Descriptions.Item label="版本">
            {str(info.data?.version)}
          </Descriptions.Item>
          <Descriptions.Item label="Python">
            {str(info.data?.python)}
          </Descriptions.Item>
          <Descriptions.Item label="PID">
            {str(info.data?.pid)}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="运行状态" loading={status.isLoading}>
        <Descriptions column={{ xs: 1, sm: 3 }} size="small">
          <Descriptions.Item label="服务">
            {status.data?.started ? (
              <Tag color="success">已启动</Tag>
            ) : (
              <Tag color="default">未启动</Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="任务总数">
            {str(status.data?.task_count)}
          </Descriptions.Item>
          <Descriptions.Item label="录制中">
            {str(status.data?.recording_count)}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="版本更新">
        <Space direction="vertical">
          <Typography.Text>
            当前版本：<Typography.Text strong>{current}</Typography.Text>
          </Typography.Text>
          {latest.isLoading ? (
            <Typography.Text type="secondary">
              正在查询最新版本…
            </Typography.Text>
          ) : latest.isError ? (
            <Typography.Text type="secondary">最新版本查询失败</Typography.Text>
          ) : hasUpdate ? (
            <Tag color="processing">发现新版本 {newest}</Tag>
          ) : (
            <Tag color="success">已是最新版本</Tag>
          )}
        </Space>
      </Card>

      <Card title="目录校验">
        <Space.Compact style={{ width: '100%', maxWidth: 480 }}>
          <Input
            placeholder="输入要校验的目录路径"
            value={dir}
            onChange={(e) => setDir(e.target.value)}
            aria-label="目录路径"
          />
          <Button
            type="primary"
            onClick={() => void onValidate()}
            loading={validateDir.isPending}
            disabled={!dir}
          >
            校验
          </Button>
        </Space.Compact>
      </Card>

      <Card title="进程操作">
        <Space>
          <Popconfirm
            title="确认重启应用？"
            okText="重启"
            cancelText="取消"
            onConfirm={() => void onRestart()}
          >
            <Button loading={restart.isPending}>重启应用</Button>
          </Popconfirm>
          <Popconfirm
            title="确认退出应用？"
            okText="退出"
            cancelText="取消"
            onConfirm={() => void onExit()}
          >
            <Button danger loading={exit.isPending}>
              退出应用
            </Button>
          </Popconfirm>
        </Space>
      </Card>
    </Flex>
  )
}
