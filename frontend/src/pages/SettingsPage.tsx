/**
 * 全局设置页（frontend-design.md §8.1）。
 *
 * 左侧分组锚点 + 右侧各分组表单卡片；每个分组独立保存
 * （PATCH /settings，body 为 { [group]: values }）。
 */
import { App as AntdApp, Alert, Anchor, Col, Row, Skeleton } from 'antd'

import { useSettings, usePatchSettings } from '../api/endpoints/settings'
import { SettingsForm } from '../components/SettingsForm'
import { toMessage } from '../lib/errors'
import {
  SETTINGS_GROUPS,
  buildPatchBody,
  getGroupValues,
} from '../lib/settingsSchema'

export function SettingsPage() {
  const { message } = AntdApp.useApp()
  const { data, isLoading, isError, error } = useSettings()
  const patch = usePatchSettings()

  if (isLoading) return <Skeleton active paragraph={{ rows: 8 }} />
  if (isError)
    return (
      <Alert
        type="error"
        showIcon
        message="加载设置失败"
        description={toMessage(error)}
      />
    )

  const settings = (data ?? {}) as Record<string, unknown>

  const handleSubmit =
    (groupKey: string) => (values: Record<string, unknown>) => {
      patch.mutate(buildPatchBody(groupKey, values), {
        onSuccess: () => message.success('设置已保存'),
        onError: (e) => message.error(toMessage(e)),
      })
    }

  return (
    <Row gutter={24}>
      <Col flex="180px">
        <Anchor
          offsetTop={80}
          items={SETTINGS_GROUPS.map((g) => ({
            key: g.key,
            href: `#settings-${g.key}`,
            title: g.title,
          }))}
        />
      </Col>
      <Col flex="auto">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {SETTINGS_GROUPS.map((group) => (
            <SettingsForm
              key={group.key}
              group={group}
              initialValues={getGroupValues(settings, group.key)}
              onSubmit={handleSubmit(group.key)}
              submitting={patch.isPending}
            />
          ))}
        </div>
      </Col>
    </Row>
  )
}
