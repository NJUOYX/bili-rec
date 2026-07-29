/**
 * 任务级设置页（frontend-design.md §8.1，null 回退全局）。
 *
 * 展示 TaskOptions 可覆盖字段：留空 = 回退全局，全局值以 placeholder 呈现。
 * 每组独立保存（PATCH /settings/tasks/{roomId}，body 为 { [group]: values }）。
 */
import {
  App as AntdApp,
  Alert,
  Anchor,
  Col,
  Row,
  Skeleton,
  Typography,
} from 'antd'
import { useParams } from 'react-router'

import {
  useSettings,
  useTaskSettings,
  usePatchTaskSettings,
} from '../api/endpoints/settings'
import { SettingsForm } from '../components/SettingsForm'
import { toMessage } from '../lib/errors'
import {
  TASK_SETTINGS_GROUPS,
  buildPatchBody,
  getGroupValues,
} from '../lib/settingsSchema'

export function TaskSettingsPage() {
  const { message } = AntdApp.useApp()
  const { roomId: roomIdParam } = useParams()
  const roomId = Number(roomIdParam)
  const valid = Number.isFinite(roomId)

  const global = useSettings()
  const task = useTaskSettings(roomId)
  const patch = usePatchTaskSettings(roomId)

  if (!valid) return <Alert type="warning" showIcon message="无效的房间号" />
  if (task.isLoading || global.isLoading)
    return <Skeleton active paragraph={{ rows: 8 }} />
  if (task.isError)
    return (
      <Alert
        type="error"
        showIcon
        message="加载任务设置失败"
        description={toMessage(task.error)}
      />
    )

  const taskSettings = (task.data ?? {}) as Record<string, unknown>
  const globalSettings = (global.data ?? {}) as Record<string, unknown>

  const handleSubmit =
    (groupKey: string) => (values: Record<string, unknown>) => {
      patch.mutate(buildPatchBody(groupKey, values), {
        onSuccess: () => message.success('任务设置已保存'),
        onError: (e) => message.error(toMessage(e)),
      })
    }

  return (
    <>
      <Typography.Title level={4}>房间 {roomId} 的设置</Typography.Title>
      <Typography.Paragraph type="secondary">
        留空字段将回退到全局设置（灰色提示为继承的全局值）。
      </Typography.Paragraph>
      <Row gutter={24}>
        <Col flex="180px">
          <Anchor
            offsetTop={80}
            items={TASK_SETTINGS_GROUPS.map((g) => ({
              key: g.key,
              href: `#settings-${g.key}`,
              title: g.title,
            }))}
          />
        </Col>
        <Col flex="auto">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            {TASK_SETTINGS_GROUPS.map((group) => (
              <SettingsForm
                key={group.key}
                group={group}
                initialValues={getGroupValues(taskSettings, group.key)}
                placeholders={getGroupValues(globalSettings, group.key)}
                onSubmit={handleSubmit(group.key)}
                submitting={patch.isPending}
              />
            ))}
          </div>
        </Col>
      </Row>
    </>
  )
}
