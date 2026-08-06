/**
 * 路径模板字段（#37）：预置下拉 + 「自定义」展开输入 + 客户端实时预览。
 *
 * 受控组件（value/onChange 由 AntD Form.Item 注入）。预置列表与校验/渲染规则
 * 均来自 lib/pathTemplate（镜像后端），保证与后端行为一致。留空（allowClear）
 * 在任务级表单中表示「回退全局」。
 */
import { Input, Select, Space, Typography } from 'antd'
import { useMemo, useState } from 'react'

import {
  PATH_TEMPLATE_PRESETS,
  isValidPathTemplate,
  renderPathTemplatePreview,
} from '../lib/pathTemplate'

/** 「自定义」选项在下拉中的哨兵值。 */
export const CUSTOM_TEMPLATE_VALUE = '__custom__'

const PRESET_OPTIONS = PATH_TEMPLATE_PRESETS.map((t) => ({
  value: t,
  label: t,
}))

export interface PathTemplateFieldProps {
  value?: string
  onChange?: (value: string | undefined) => void
  placeholder?: string
}

export function PathTemplateField({
  value,
  onChange,
  placeholder,
}: PathTemplateFieldProps) {
  const isPreset = value != null && PATH_TEMPLATE_PRESETS.includes(value)
  const hasCustomValue = value != null && value !== '' && !isPreset
  // 是否展开自定义输入框：显式选中「自定义」，或当前值不是任一预置。
  // 值为预置时强制收起，避免重置（resetFields）后残留展开态。
  const [customMode, setCustomMode] = useState(hasCustomValue)
  const showCustomInput = !isPreset && (customMode || hasCustomValue)

  const selectValue = showCustomInput
    ? CUSTOM_TEMPLATE_VALUE
    : value || undefined

  const handleSelect = (selected: string | undefined) => {
    if (selected === CUSTOM_TEMPLATE_VALUE) {
      setCustomMode(true)
      return
    }
    setCustomMode(false)
    // 选中预置或清空（allowClear → undefined，即任务级回退全局）。
    onChange?.(selected ?? undefined)
  }

  const valid = value != null && value !== '' && isValidPathTemplate(value)
  const preview = useMemo(
    () => (valid && value ? renderPathTemplatePreview(value) : ''),
    [valid, value],
  )

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={4}>
      <Select
        allowClear
        style={{ width: '100%' }}
        value={selectValue}
        placeholder={placeholder ?? '选择预置模板或自定义'}
        options={[
          ...PRESET_OPTIONS,
          { value: CUSTOM_TEMPLATE_VALUE, label: '自定义…' },
        ]}
        onChange={handleSelect}
        data-testid="path-template-select"
      />
      {showCustomInput && (
        <Input
          value={value ?? ''}
          placeholder="{roomid} - {uname}/blive_{roomid}_{year}-{month}-{day}"
          onChange={(e) => onChange?.(e.target.value || undefined)}
          data-testid="path-template-input"
        />
      )}
      {value != null && value !== '' && !valid && (
        <Typography.Text type="danger" data-testid="path-template-error">
          模板无效：每段路径须至少含一个合法占位符
        </Typography.Text>
      )}
      {preview && (
        <Typography.Text type="secondary" data-testid="path-template-preview">
          预览：{preview}
        </Typography.Text>
      )}
    </Space>
  )
}
