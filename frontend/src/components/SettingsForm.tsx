/**
 * 设置分组表单卡片（frontend-design.md §8.1/§8.2）。
 *
 * 由 GroupDescriptor 驱动渲染各字段；支持任务级「留空回退全局」语义：
 * 传入 placeholders（继承的全局值）作为占位提示，未填字段不纳入提交 body。
 */
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
} from 'antd'

import type { FieldDescriptor, GroupDescriptor } from '../lib/settingsSchema'

export interface SettingsFormProps {
  group: GroupDescriptor
  /** 当前分组已保存的值。 */
  initialValues: Record<string, unknown>
  /** 提交回调：仅收到本表单字段的当前值。 */
  onSubmit: (values: Record<string, unknown>) => void
  submitting?: boolean
  /** 任务级：各字段继承的全局值，作为 placeholder 呈现。 */
  placeholders?: Record<string, unknown>
}

function renderControl(
  field: FieldDescriptor,
  placeholder: unknown,
): React.ReactNode {
  const ph = placeholder != null ? String(placeholder) : field.placeholder
  switch (field.type) {
    case 'switch':
      return <Switch />
    case 'number':
      return (
        <InputNumber
          style={{ width: '100%' }}
          min={field.min}
          max={field.max}
          step={field.step}
          placeholder={ph}
          controls={false}
        />
      )
    case 'select':
      return (
        <Select
          allowClear
          options={field.options}
          placeholder={ph ?? '请选择'}
        />
      )
    case 'textarea':
      return (
        <Input.TextArea
          autoSize={{ minRows: 1, maxRows: 4 }}
          placeholder={ph}
        />
      )
    case 'stringList':
      return (
        <Select
          mode="tags"
          tokenSeparators={[',', ' ']}
          placeholder={ph ?? '输入后回车添加'}
        />
      )
    case 'text':
    default:
      return <Input placeholder={ph} />
  }
}

export function SettingsForm({
  group,
  initialValues,
  onSubmit,
  submitting,
  placeholders,
}: SettingsFormProps) {
  const [form] = Form.useForm()

  return (
    <Card title={group.title} id={`settings-${group.key}`}>
      <Form
        form={form}
        layout="vertical"
        initialValues={initialValues}
        onFinish={onSubmit}
      >
        {group.fields.map((field) => (
          <Form.Item
            key={field.key}
            name={field.key}
            label={field.label}
            help={field.help}
            valuePropName={field.type === 'switch' ? 'checked' : 'value'}
            rules={
              field.type === 'number' &&
              (field.min != null || field.max != null)
                ? [{ type: 'number', min: field.min, max: field.max }]
                : undefined
            }
          >
            {renderControl(field, placeholders?.[field.key])}
          </Form.Item>
        ))}
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={submitting}>
              保存
            </Button>
            <Button onClick={() => form.resetFields()}>重置</Button>
          </Space>
        </Form.Item>
      </Form>
    </Card>
  )
}
