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
import { usePendingGroups } from '../lib/pendingGroups'
import {
  SETTINGS_GROUPS,
  buildPatchBody,
  getGroupValues,
} from '../lib/settingsSchema'

export function SettingsPage() {
  const { message } = AntdApp.useApp()
  const { data, isLoading, isError, error } = useSettings()
  const patch = usePatchSettings()
  const pending = usePendingGroups()

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
      pending.setPending(groupKey, true)
      // 用 mutateAsync 的「每次调用一个 promise」：共用 mutation 时，传给 mutate
      // 的回调只会为最后一次调用触发，先前那次的 loading 将永远无法收尾。
      void patch
        .mutateAsync(buildPatchBody(groupKey, values))
        .then(() => message.success('设置已保存'))
        .catch((e: unknown) => message.error(toMessage(e)))
        .finally(() => pending.setPending(groupKey, false))
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
              submitting={pending.isPending(group.key)}
            />
          ))}
        </div>
      </Col>
    </Row>
  )
}
